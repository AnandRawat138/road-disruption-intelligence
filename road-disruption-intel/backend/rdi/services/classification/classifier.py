"""Classification workflow for a single article.

Every attempt is stored as a new ``Classification`` version (including
failures) recording provider, model, prompt version, raw output and the
validation outcome. The provider is never switched silently: if the selected
provider fails, the failure is recorded and the operator may explicitly retry
with another provider.
"""
from __future__ import annotations

import logging
import random
import time
from datetime import timedelta

import httpx
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from ...db.models import Article, Classification, utcnow
from .. import audit, incidents, settings_store
from ..geo.geocoder import Geocoder, normalize_city, normalize_state
from ..llm.providers import LLMError, build_provider
from ..text import new_id, strip_publisher_suffix
from .schema import (OUTPUT_SCHEMA, PROMPT_VERSION, SYSTEM_PROMPT, build_user_prompt, extract_json,
                     validate_output)

log = logging.getLogger(__name__)

# State/UT names that unambiguously denote a single city.
CITY_STATES = {"Delhi": "Delhi", "Chandigarh": "Chandigarh", "Puducherry": "Puducherry"}


def article_source_text(article: Article) -> str:
    parts = [article.title or ""]
    if article.summary_text and article.summary_text.strip() != (article.title or "").strip():
        parts.append(article.summary_text)
    if article.body_text:
        parts.append(article.body_text)
    return "\n".join(p for p in parts if p)


def is_headline_only(article: Article) -> bool:
    title = (article.title or "").strip().lower()
    summary = (article.summary_text or "").strip().lower()
    extra = summary.replace(title, "").strip() if summary else ""
    return not article.body_text and len(extra) < 60


def resolve_provider_config(db: Session, provider_name: str | None) -> tuple[str, dict]:
    cfg = settings_store.get(db, "llm")
    name = provider_name or cfg.get("active_provider") or "ollama"
    pcfg = (cfg.get("providers") or {}).get(name)
    if pcfg is None:
        raise LLMError("CONFIG", f"Provider '{name}' is not configured")
    return name, pcfg


def _call_with_retries(provider, system: str, user: str, retries: int) -> tuple[object | None, dict | None, str, list[str]]:
    """Returns (result, parsed_json, raw_text, attempt_errors)."""
    errors: list[str] = []
    raw_text = ""
    for attempt in range(retries + 1):
        try:
            res = provider.generate_json(system, user, OUTPUT_SCHEMA)
        except LLMError as e:
            errors.append(f"attempt {attempt + 1}: {e.kind}: {e}")
            if not e.retryable or attempt == retries:
                raise LLMError(e.kind, "; ".join(errors), e.retryable, e.status) from e
            time.sleep(min(30.0, (2 ** attempt) + random.uniform(0, 1)))
            continue
        raw_text = res.text
        parsed = res.parsed if res.parsed is not None else extract_json(res.text)
        if parsed is not None:
            return res, parsed, raw_text, errors
        errors.append(f"attempt {attempt + 1}: malformed JSON output")
    return None, None, raw_text, errors


def classify_article(db: Session, article: Article, provider_name: str | None = None, actor: str = "system",
                     http_client: httpx.Client | None = None, geocoder: Geocoder | None = None) -> Classification:
    ccfg = settings_store.get(db, "classification")
    name, pcfg = resolve_provider_config(db, provider_name)
    provider = build_provider(name, pcfg, http_client)
    source_text = article_source_text(article)
    user = build_user_prompt(article.title, article.source_name, article.published_at, article.retrieved_at,
                             source_text, int(ccfg.get("max_input_chars", 4000)))
    article.classification_attempts = (article.classification_attempts or 0) + 1
    article.classification_status = "PROCESSING"
    # Commit now so no write transaction (SQLite write lock) is held during the slow model call.
    db.commit()

    cls = Classification(id=new_id("CLS_"), article_id=article.id, origin="MODEL", provider=name,
                         model=pcfg.get("model"), prompt_version=PROMPT_VERSION, created_by=actor,
                         input_chars=len(user))
    t0 = time.monotonic()
    try:
        res, parsed, raw_text, attempt_errors = _call_with_retries(provider, SYSTEM_PROMPT, user,
                                                                   int(ccfg.get("retries", 2)))
    except LLMError as e:
        cls.status, cls.error = "FAILED", str(e)[:2000]
        cls.latency_ms = int((time.monotonic() - t0) * 1000)
        cls.validation_status = "FAILED"
        return _store(db, article, cls, actor, link=False)

    cls.latency_ms = int((time.monotonic() - t0) * 1000)
    cls.raw_output = (raw_text or "")[:20000]
    if res is not None:
        cls.model = res.model or cls.model
    if parsed is None:
        cls.status, cls.validation_status = "INVALID", "FAILED"
        cls.error = "; ".join(attempt_errors) or "model output was not valid JSON"
        return _store(db, article, cls, actor, link=False)

    fields, issues, fatal = validate_output(parsed, source_text, article.published_at)
    if fatal:
        cls.status, cls.validation_status = "INVALID", "FAILED"
        cls.error = "; ".join(fatal)
        cls.validation_issues = fatal + issues
        return _store(db, article, cls, actor, link=False)

    for key in ("relevance", "category", "summary", "country", "state", "city", "locality", "road_name",
                "highway_number", "direction", "affected_segment", "event_start", "event_end", "time_status",
                "severity", "reported_delay", "advisory_action", "evidence_excerpt", "evidence_verified",
                "model_confidence", "missing_fields"):
        setattr(cls, key, fields.get(key))
    if not cls.summary:
        cls.summary = strip_publisher_suffix(article.title or "", article.source_name)[:600]
    city_c, city_state = normalize_city(cls.city)
    cls.city = city_c
    state_c = normalize_state(cls.state)
    if cls.state and not state_c:
        issues.append(f"state '{cls.state}' is not a recognised Indian state/UT – removed")
    cls.state = state_c or city_state
    if not cls.city and cls.state in CITY_STATES:
        cls.city = CITY_STATES[cls.state]  # union territories that are a single city
    if attempt_errors:
        issues.append(f"succeeded after retry ({len(attempt_errors)} failed attempt(s))")
    cls.status = "VALID"

    if cls.relevance in ("RELEVANT", "NEEDS_REVIEW"):
        geo = (geocoder or Geocoder(db)).resolve(cls.locality, cls.city, cls.state)
        _apply_geo(cls, geo)
    else:
        cls.geo_status = "UNRESOLVED"

    reasons = review_reasons(cls, article, ccfg, issues)
    cls.validation_issues = issues
    cls.validation_status = "WARNINGS" if issues else "PASSED"
    cls.review_reasons = reasons
    cls.needs_review = bool(reasons)
    return _store(db, article, cls, actor, link=True)


def _apply_geo(cls: Classification, geo) -> None:
    cls.geo_status, cls.geo_precision, cls.geo_method = geo.status, geo.precision, geo.method
    cls.geo_query, cls.geo_display_name, cls.geo_confidence = geo.query, geo.display_name, geo.confidence
    cls.latitude, cls.longitude = geo.latitude, geo.longitude


def review_reasons(cls: Classification, article: Article, ccfg: dict, issues: list[str]) -> list[str]:
    reasons: list[str] = []
    if cls.relevance == "NEEDS_REVIEW":
        reasons.append("Model marked the record as ambiguous")
    if cls.relevance != "RELEVANT":
        return reasons
    if ccfg.get("review_low_confidence", True) and cls.model_confidence == "LOW":
        reasons.append("Low model confidence")
    if ccfg.get("review_unverified_evidence", True) and not cls.evidence_verified:
        reasons.append("Evidence excerpt not found verbatim in the source")
    if ccfg.get("review_unresolved_location", True) and cls.geo_status == "UNRESOLVED":
        reasons.append("Location could not be resolved")
    if cls.geo_precision == "STATE":
        reasons.append("Location known only at state level")
    if any("inferred" in i for i in issues):
        reasons.append("Location inferred rather than stated")
    if any(("removed" in i and "date" in i) or "before event_start" in i for i in issues):
        reasons.append("Date/time problems in extraction")
    if ccfg.get("review_headline_only", False) and is_headline_only(article):
        reasons.append("Headline-only evidence")
    if (article.published_at and cls.time_status in ("ONGOING", "UPCOMING")
            and utcnow() - article.published_at > timedelta(days=30)):
        reasons.append("Article is more than 30 days old – status may be outdated")
    return reasons


def _store(db: Session, article: Article, cls: Classification, actor: str, link: bool) -> Classification:
    prev_version = db.scalar(select(Classification.version).where(Classification.article_id == article.id)
                             .order_by(Classification.version.desc()).limit(1)) or 0
    cls.version = prev_version + 1
    if cls.status == "VALID":
        previous = db.get(Classification, article.current_classification_id) if article.current_classification_id else None
        db.execute(update(Classification).where(Classification.article_id == article.id,
                                                Classification.is_current.is_(True)).values(is_current=False))
        cls.is_current = True
        article.current_classification_id = cls.id
        article.classification_status = "CLASSIFIED"
        prior_review = article.review_status
        unchanged = previous is not None and (previous.relevance, previous.category) == (cls.relevance, cls.category)
        if prior_review in ("APPROVED", "REJECTED") and unchanged:
            pass  # operator decision still applies to the same outcome
        elif cls.relevance == "RELEVANT" or cls.needs_review:
            article.review_status = "PENDING_REVIEW"
        else:
            article.review_status = "NOT_REQUIRED"
        if prior_review in ("APPROVED", "REJECTED") and article.review_status != prior_review:
            audit.record(db, "article", article.id, "review_cleared", actor, old=prior_review,
                         new=article.review_status, note="Reclassification changed relevance/category")
    else:
        # Failed attempts are kept for audit but never replace a previous valid result.
        cls.is_current = False
        article.classification_status = "CLASSIFIED" if article.current_classification_id else "FAILED"
    db.add(cls)
    db.flush()
    audit.record(db, "article", article.id, "classified" if cls.status == "VALID" else "classification_failed",
                 actor, classification_id=cls.id, provider=cls.provider, model=cls.model, status=cls.status,
                 relevance=cls.relevance, category=cls.category, error=(cls.error or "")[:300])
    if link and cls.status == "VALID":
        incidents.link_article(db, article, cls, actor)
    return cls


EDITABLE_FIELDS = {"relevance", "category", "summary", "country", "state", "city", "locality", "road_name",
                   "highway_number", "direction", "affected_segment", "event_start", "event_end", "time_status",
                   "severity", "reported_delay", "advisory_action", "evidence_excerpt", "latitude", "longitude"}


def human_correction(db: Session, article: Article, changes: dict, actor: str, note: str | None = None) -> Classification:
    """Create a new HUMAN classification version based on the current one."""
    from .schema import CATEGORY_CODES, RELEVANCE, SEVERITY, TIME_STATUS, normalize_highway
    from ..text import parse_timestamp
    from ..geo.geocoder import valid_india_coords

    base = db.get(Classification, article.current_classification_id) if article.current_classification_id else None
    new = Classification(id=new_id("CLS_"), article_id=article.id, origin="HUMAN", provider="human",
                         model=None, prompt_version=None, created_by=actor, status="VALID")
    if base is not None:
        for col in Classification.__table__.columns.keys():
            if col not in ("id", "version", "is_current", "origin", "provider", "model", "prompt_version",
                           "created_at", "created_by", "raw_output", "error", "latency_ms", "input_chars"):
                setattr(new, col, getattr(base, col))
    new.id = new_id("CLS_")
    new.origin, new.provider, new.created_by, new.status = "HUMAN", "human", actor, "VALID"
    old_values = {}
    for key, value in changes.items():
        if key not in EDITABLE_FIELDS:
            raise ValueError(f"Field '{key}' cannot be edited")
        if isinstance(value, str):
            value = value.strip() or None
        if key == "relevance" and value not in RELEVANCE:
            raise ValueError("Invalid relevance")
        if key == "category" and value not in CATEGORY_CODES:
            raise ValueError("Invalid category")
        if key == "severity" and value not in SEVERITY:
            raise ValueError("Invalid severity")
        if key == "time_status" and value not in TIME_STATUS:
            raise ValueError("Invalid time status")
        if key in ("event_start", "event_end") and value is not None:
            parsed = parse_timestamp(value)
            if parsed is None:
                raise ValueError(f"Invalid date for {key}")
            value = parsed
        if key == "highway_number":
            value = normalize_highway(value)
        old_values[key] = getattr(new, key)
        setattr(new, key, value)
    if "latitude" in changes or "longitude" in changes:
        if new.latitude is None and new.longitude is None:
            new.geo_status, new.geo_precision, new.geo_method = "UNRESOLVED", None, "MANUAL"
        elif not valid_india_coords(new.latitude, new.longitude):
            raise ValueError("Coordinates must be a valid latitude/longitude inside India")
        else:
            new.latitude, new.longitude = float(new.latitude), float(new.longitude)
            new.geo_status, new.geo_precision, new.geo_method, new.geo_confidence = "MANUAL", "MANUAL", "MANUAL", "HIGH"
    elif any(k in changes for k in ("city", "state", "locality")):
        city_c, city_state = normalize_city(new.city)
        new.city = city_c
        new.state = normalize_state(new.state) or city_state
        _apply_geo(new, Geocoder(db).resolve(new.locality, new.city, new.state))
    new.needs_review = False
    new.review_reasons = []
    new.validation_issues = list(new.validation_issues or []) + [f"Corrected by {actor}" + (f": {note}" if note else "")]
    db.execute(update(Classification).where(Classification.article_id == article.id,
                                            Classification.is_current.is_(True)).values(is_current=False))
    prev_version = db.scalar(select(Classification.version).where(Classification.article_id == article.id)
                             .order_by(Classification.version.desc()).limit(1)) or 0
    new.version = prev_version + 1
    new.is_current = True
    db.add(new)
    article.current_classification_id = new.id
    article.classification_status = "CLASSIFIED"
    db.flush()
    audit.record(db, "article", article.id, "corrected", actor, classification_id=new.id,
                 old=old_values, new={k: getattr(new, k) for k in changes}, note=note)
    incidents.link_article(db, article, new, actor)
    return new
