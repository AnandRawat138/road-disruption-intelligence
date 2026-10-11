"""LLM configuration, secrets, application settings, classification triggers and system health."""
from __future__ import annotations

import platform
import time
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from .. import __version__, secrets
from ..config import settings
from ..db.models import Article, Classification, Source, utcnow
from ..db.session import backup_database, get_db
from ..services import audit, ollama_setup, scheduler, settings_store
from ..services.classification.classifier import resolve_provider_config
from ..services.classification.schema import (OUTPUT_SCHEMA, PROMPT_VERSION, SYSTEM_PROMPT, build_user_prompt,
                                               extract_json, validate_output)
from ..services.jobs import runner
from ..services.llm.providers import PROVIDERS, LLMError, build_provider
from .common import actor_from, iso

router = APIRouter(tags=["configuration"])

PUBLIC_SETTING_KEYS = {"branding", "map"}
EDITABLE_SETTING_KEYS = {"branding", "classification", "incidents", "alerts", "map", "acquisition", "setup"}


# ----------------------------------------------------------------------------- LLM
@router.get("/api/llm/config")
def llm_config(db: Session = Depends(get_db)):
    cfg = settings_store.get(db, "llm")
    return {"active_provider": cfg["active_provider"], "fallback_provider": cfg.get("fallback_provider") or "",
            "providers": cfg["providers"], "last_tests": cfg.get("last_tests", {}),
            "available_providers": list(PROVIDERS.keys()), "prompt_version": PROMPT_VERSION,
            "secrets": [secrets.secret_status(n) for n in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY")],
            "secret_storage": ("Keys entered here are stored server-side in runtime/secrets.json (plain JSON, "
                               "protected only by Windows file permissions, never sent to the browser). Keys set as "
                               "environment variables take precedence and cannot be removed from the UI.")}


class ProviderSettings(BaseModel):
    base_url: str | None = Field(default=None, max_length=300)
    model: str | None = Field(default=None, max_length=120)
    temperature: float | None = Field(default=None, ge=0, le=2)
    max_tokens: int | None = Field(default=None, ge=128, le=8192)
    timeout_seconds: int | None = Field(default=None, ge=5, le=600)
    structured_output: str | None = Field(default=None, pattern="^(json_schema|json_object|none)$")
    label: str | None = Field(default=None, max_length=60)


class LLMConfigIn(BaseModel):
    active_provider: str | None = None
    fallback_provider: str | None = None
    providers: dict[str, ProviderSettings] = Field(default_factory=dict)


@router.put("/api/llm/config")
def update_llm_config(body: LLMConfigIn, db: Session = Depends(get_db), actor: str = Depends(actor_from)):
    for name in [body.active_provider, body.fallback_provider, *body.providers.keys()]:
        if name and name not in PROVIDERS:
            raise HTTPException(422, f"Unknown provider {name}")
    patch: dict = {}
    if body.active_provider:
        patch["active_provider"] = body.active_provider
    if body.fallback_provider is not None:
        patch["fallback_provider"] = body.fallback_provider
    provs = {}
    for name, p in body.providers.items():
        d = p.model_dump(exclude_none=True)
        if "base_url" in d and d["base_url"] and not d["base_url"].startswith(("http://", "https://")):
            raise HTTPException(422, "Base URL must start with http:// or https://")
        provs[name] = d
    if provs:
        patch["providers"] = provs
    new = settings_store.patch(db, "llm", patch)
    audit.record(db, "settings", "llm", "updated", actor, changes=patch)
    db.commit()
    return {"active_provider": new["active_provider"], "providers": new["providers"]}


class SecretIn(BaseModel):
    value: str = Field(min_length=1, max_length=4096)


@router.get("/api/secrets")
def list_secrets():
    return {"secrets": secrets.all_statuses()}


@router.put("/api/secrets/{name}")
def put_secret(name: str, body: SecretIn, db: Session = Depends(get_db), actor: str = Depends(actor_from)):
    try:
        secrets.set_secret(name, body.value)
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    audit.record(db, "secret", name, "set", actor)  # value is never logged
    db.commit()
    return secrets.secret_status(name)


@router.delete("/api/secrets/{name}")
def delete_secret(name: str, db: Session = Depends(get_db), actor: str = Depends(actor_from)):
    try:
        existed = secrets.delete_secret(name)
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    audit.record(db, "secret", name, "deleted", actor)
    db.commit()
    return {**secrets.secret_status(name), "removed": existed}


class TestIn(BaseModel):
    provider: str


@router.post("/api/llm/test")
def test_llm(body: TestIn, db: Session = Depends(get_db)):
    """Connection test: list models and run a tiny structured generation."""
    try:
        name, pcfg = resolve_provider_config(db, body.provider)
        prov = build_provider(name, pcfg)
    except LLMError as e:
        return {"ok": False, "stage": "config", "error": e.as_dict()}
    result: dict = {"provider": name, "model": pcfg.get("model"), "base_url": pcfg.get("base_url"), "tested_at": iso(utcnow())}
    try:
        models = prov.list_models()
        result["models"] = models[:200]
        result["model_available"] = (pcfg.get("model") in models) if models else None
    except LLMError as e:
        result.update(ok=False, stage="list_models", error=e.as_dict())
        _save_test(db, name, result)
        return result
    if result.get("model_available") is False and name == "ollama":
        result.update(ok=False, stage="model_check",
                      error={"kind": "MODEL_NOT_FOUND", "message": f"Model '{pcfg.get('model')}' is not installed in Ollama."})
        _save_test(db, name, result)
        return result
    schema = {"type": "object", "properties": {"status": {"type": "string", "enum": ["ok"]}}, "required": ["status"]}
    t0 = time.monotonic()
    try:
        res = prov.generate_json("Reply with JSON only.", 'Return {"status": "ok"}.', schema)
        parsed = res.parsed or extract_json(res.text)
        result.update(ok=bool(parsed and parsed.get("status") == "ok"), stage="generation",
                      latency_ms=int((time.monotonic() - t0) * 1000), sample_output=(res.text or "")[:200])
        if not result["ok"]:
            result["error"] = {"kind": "BAD_RESPONSE", "message": "Model responded but not with the requested JSON."}
    except LLMError as e:
        result.update(ok=False, stage="generation", error=e.as_dict())
    _save_test(db, name, result)
    return result


def _save_test(db: Session, name: str, result: dict) -> None:
    cfg = settings_store.get(db, "llm")
    tests = dict(cfg.get("last_tests") or {})
    tests[name] = {k: result.get(k) for k in ("ok", "stage", "tested_at", "model", "latency_ms", "error", "model_available")}
    settings_store.patch(db, "llm", {"last_tests": tests})
    db.commit()


@router.get("/api/llm/models")
def llm_models(provider: str, db: Session = Depends(get_db)):
    try:
        name, pcfg = resolve_provider_config(db, provider)
        return {"provider": name, "models": build_provider(name, pcfg).list_models()}
    except LLMError as e:
        raise HTTPException(502, e.as_dict()) from e


class SampleIn(BaseModel):
    provider: str | None = None
    title: str = Field(min_length=3, max_length=500)
    text: str = Field(default="", max_length=8000)
    source: str | None = Field(default="TEST RECORD", max_length=100)


@router.post("/api/llm/test-classification")
def test_classification(body: SampleIn, db: Session = Depends(get_db)):
    """Classify a clearly-labelled test record. Nothing is written to the records database."""
    try:
        name, pcfg = resolve_provider_config(db, body.provider)
        prov = build_provider(name, pcfg)
    except LLMError as e:
        return {"ok": False, "error": e.as_dict()}
    source_text = "\n".join(x for x in (body.title, body.text) if x)
    user = build_user_prompt(body.title, body.source, utcnow(), utcnow(), body.text or body.title,
                             int(settings_store.get(db, "classification").get("max_input_chars", 4000)))
    try:
        res = prov.generate_json(SYSTEM_PROMPT, user, OUTPUT_SCHEMA)
    except LLMError as e:
        return {"ok": False, "provider": name, "model": pcfg.get("model"), "error": e.as_dict()}
    parsed = res.parsed or extract_json(res.text)
    if parsed is None:
        return {"ok": False, "provider": name, "model": res.model, "raw_output": res.text[:4000],
                "error": {"kind": "INVALID_JSON", "message": "Model output was not valid JSON"}}
    fields, issues, fatal = validate_output(parsed, source_text, utcnow())
    return {"ok": not fatal, "test_record": True, "provider": name, "model": res.model, "latency_ms": res.latency_ms,
            "fields": {k: (iso(v) if hasattr(v, "isoformat") else v) for k, v in fields.items()},
            "validation_issues": issues, "fatal": fatal, "raw_output": res.text[:4000]}


@router.get("/api/llm/ollama/status")
def ollama_status(db: Session = Depends(get_db)):
    base = settings_store.get(db, "llm")["providers"]["ollama"]["base_url"]
    hw = ollama_setup.hardware_info()
    return {"ollama": ollama_setup.detect(base), "hardware": hw, "recommendation": ollama_setup.recommend(hw),
            "notes": ["Installing Ollama and downloading models requires an internet connection.",
                      "After a model is downloaded, local classification runs without internet access; news sources, "
                      "geocoding and map tiles still need internet."]}


class PullIn(BaseModel):
    model: str = Field(pattern=r"^[A-Za-z0-9._:/-]{2,80}$")
    confirm: bool = False


@router.post("/api/llm/ollama/pull")
def ollama_pull(body: PullIn, db: Session = Depends(get_db), actor: str = Depends(actor_from)):
    if not body.confirm:
        raise HTTPException(400, "Downloading a model requires explicit confirmation (confirm=true)")
    base = settings_store.get(db, "llm")["providers"]["ollama"]["base_url"]
    st = ollama_setup.detect(base)
    if not st["reachable"]:
        raise HTTPException(409, st["error"] or "Ollama is not reachable")
    job = runner().submit("ollama_pull", {"base_url": base, "model": body.model}, actor, dedup_key=f"pull:{body.model}")
    audit.record(db, "llm", "ollama", "pull_requested", actor, model=body.model)
    db.commit()
    return {"job_id": job.id}


# ----------------------------------------------------------------------------- classification triggers
class ClassifyIn(BaseModel):
    article_ids: list[str] | None = Field(default=None, max_length=5000)
    filters: dict | None = None
    limit: int = Field(default=50, ge=1, le=5000)
    provider: str | None = None
    reclassify: bool = False


@router.post("/api/classification/run")
def run_classification(body: ClassifyIn, db: Session = Depends(get_db), actor: str = Depends(actor_from)):
    if not body.article_ids and body.filters is None:
        raise HTTPException(422, "Provide article_ids or filters")
    try:
        name, _ = resolve_provider_config(db, body.provider)
    except LLMError as e:
        raise HTTPException(422, str(e)) from e
    params = body.model_dump()
    params["provider"] = name
    params["actor"] = actor
    job = runner().submit("classify", params, actor)
    return {"job_id": job.id, "provider": name}


@router.get("/api/classification/stats")
def classification_stats(db: Session = Depends(get_db)):
    by_status = dict(db.execute(select(Article.classification_status, func.count()).group_by(Article.classification_status)).all())
    by_review = dict(db.execute(select(Article.review_status, func.count()).group_by(Article.review_status)).all())
    by_rel = dict(db.execute(select(Classification.relevance, func.count()).where(Classification.is_current.is_(True))
                             .group_by(Classification.relevance)).all())
    by_model = [{"provider": p, "model": m, "count": c} for p, m, c in db.execute(
        select(Classification.provider, Classification.model, func.count()).where(Classification.is_current.is_(True))
        .group_by(Classification.provider, Classification.model))]
    needs = db.scalar(select(func.count(Classification.id)).where(Classification.is_current.is_(True),
                                                                   Classification.needs_review.is_(True))) or 0
    return {"by_classification_status": by_status, "by_review_status": by_review, "by_relevance": by_rel,
            "by_model": by_model, "flagged_for_review": needs, "prompt_version": PROMPT_VERSION}


# ----------------------------------------------------------------------------- settings
@router.get("/api/settings/public")
def public_settings(db: Session = Depends(get_db)):
    return {k: settings_store.get(db, k) for k in PUBLIC_SETTING_KEYS} | {
        "version": __version__, "categories": [{"code": c, "label": l} for c, l in settings_store.CATEGORIES],
        "auth_required": bool(settings.access_token)}


@router.get("/api/settings/{key}")
def get_setting(key: str, db: Session = Depends(get_db)):
    if key not in EDITABLE_SETTING_KEYS:
        raise HTTPException(404, "Unknown settings group")
    return settings_store.get(db, key)


@router.put("/api/settings/{key}")
def put_setting(key: str, body: dict, db: Session = Depends(get_db), actor: str = Depends(actor_from)):
    if key not in EDITABLE_SETTING_KEYS:
        raise HTTPException(404, "Unknown settings group")
    current = settings_store.get(db, key)
    unknown = [k for k in body if k not in current]
    if unknown:
        raise HTTPException(422, f"Unknown setting(s): {', '.join(unknown)}")
    for k, v in body.items():
        if isinstance(current[k], bool) and not isinstance(v, bool):
            raise HTTPException(422, f"{k} must be true/false")
        if isinstance(current[k], (int, float)) and not isinstance(current[k], bool) and not isinstance(v, (int, float)):
            raise HTTPException(422, f"{k} must be a number")
        if isinstance(v, str) and len(v) > 2000:
            raise HTTPException(422, f"{k} is too long")
    if key == "incidents":
        for k in ("stale_after_hours", "link_window_hours"):
            if k in body and not (1 <= float(body[k]) <= 24 * 60):
                raise HTTPException(422, f"{k} must be between 1 and 1440 hours")
    new = settings_store.patch(db, key, body)
    audit.record(db, "settings", key, "updated", actor, changes=body)
    db.commit()
    return new


# ----------------------------------------------------------------------------- system
@router.get("/api/health")
def health():
    return {"status": "ok", "version": __version__, "time": iso(utcnow())}


@router.get("/api/ready")
def ready(db: Session = Depends(get_db)):
    checks = {}
    try:
        db.execute(text("SELECT 1"))
        checks["database"] = {"ok": True}
    except Exception as e:
        checks["database"] = {"ok": False, "error": type(e).__name__}
    checks["scheduler"] = {"ok": True, "running": scheduler.state.get("running"), "reason": scheduler.state.get("reason")}
    checks["historical_data_dir"] = {"ok": settings.historical_data_dir.is_dir()}
    checks["frontend_build"] = {"ok": (settings.frontend_dist / "index.html").is_file()}
    ok = checks["database"]["ok"]
    return {"ready": ok, "checks": checks}


@router.get("/api/system/info")
def system_info(db: Session = Depends(get_db)):
    llm = settings_store.get(db, "llm")
    active = llm["active_provider"]
    db_path = settings.sqlite_path
    backups = sorted(settings.backups_dir.glob("*.db"), key=lambda p: p.stat().st_mtime, reverse=True) \
        if settings.backups_dir.is_dir() else []
    return {
        "version": __version__, "python": platform.python_version(), "platform": platform.platform(),
        "database": {"path": str(db_path) if db_path else "external",
                     "size_mb": round(db_path.stat().st_size / 1e6, 1) if db_path and db_path.exists() else None},
        "runtime_dir": str(settings.runtime_dir), "historical_data_dir": str(settings.historical_data_dir),
        "bind": f"{settings.host}:{settings.port}", "auth_enabled": bool(settings.access_token),
        "scheduler": {**scheduler.state, "last_tick": iso(scheduler.state.get("last_tick"))},
        "llm": {"active_provider": active, "model": llm["providers"].get(active, {}).get("model"),
                "last_test": (llm.get("last_tests") or {}).get(active)},
        "sources_enabled": db.scalar(select(func.count(Source.id)).where(Source.enabled.is_(True))) or 0,
        "backups": [{"name": p.name, "size_mb": round(p.stat().st_size / 1e6, 1),
                     "created": iso(datetime.fromtimestamp(p.stat().st_mtime, timezone.utc).replace(tzinfo=None))} for p in backups[:20]],
        "internet_required_for": ["Live news sources (Google News, GDELT, NewsAPI, GNews, Reddit)",
                                  "Online geocoding (Nominatim) for localities not in the offline gazetteer",
                                  "Map basemap tiles", "Cloud LLM providers (OpenAI-compatible, Anthropic)",
                                  "Installing Ollama and downloading models"],
        "works_offline": ["Browsing, searching and exporting stored records", "Data import", "Review workflow",
                          "Classification with a local Ollama model that is already downloaded",
                          "City-level geocoding via the built-in gazetteer"],
    }


@router.post("/api/system/backup")
def make_backup(db: Session = Depends(get_db), actor: str = Depends(actor_from)):
    path = backup_database("manual")
    if path is None:
        raise HTTPException(409, "Backups are only supported for the local SQLite database")
    audit.record(db, "system", "database", "backup", actor, file=Path(path).name)
    db.commit()
    return {"file": Path(path).name}
