"""Background job implementations (registered with the job runner on import)."""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

from sqlalchemy import select

from ..db.models import Article, Classification
from ..db.session import SessionLocal
from . import importer, settings_store
from .acquisition import run_source
from .classification.classifier import has_llm_or_human_result, classify_article, resolve_provider_config
from .classification.schema import PROMPT_VERSION
from .llm.providers import LLMError, build_provider
from .jobs import JobContext, handler

log = logging.getLogger(__name__)
MAX_CLASSIFY_PER_JOB = 5000


@handler("import")
def _import(ctx: JobContext, params: dict) -> dict:
    with SessionLocal() as db:
        def progress(done: int, total: int, msg: str) -> bool:
            ctx.update(processed=done, total=total, message=msg)
            return not ctx.cancelled()
        batch = importer.run_import(db, params["batch_id"], progress)
        ctx.update(processed=batch.discovered, total=batch.discovered, succeeded=batch.imported + batch.duplicate,
                   failed=batch.invalid + batch.failed)
        return {"batch_id": batch.id, "status": batch.status, "message": batch.message or batch.status,
                "_status": "FAILED" if batch.status == "FAILED" else "COMPLETED"}


@handler("fetch_source")
def _fetch(ctx: JobContext, params: dict) -> dict:
    with SessionLocal() as db:
        ctx.update(message=f"Fetching {params['source_id']}")
        run = run_source(db, params["source_id"], params.get("trigger", "MANUAL"))
        msg = (f"{run.status}: fetched {run.fetched}, new {run.new}, duplicates {run.duplicates}"
               + (f" – {run.error[:200]}" if run.error else ""))
        ctx.update(processed=run.fetched, total=run.fetched, succeeded=run.new, failed=run.invalid, message=msg)
        return {"run_id": run.id, "status": run.status, "message": msg,
                "_status": "COMPLETED" if run.status in ("OK", "PARTIAL") else "FAILED"}


def select_articles_for_classification(db, params: dict) -> list[str]:
    if params.get("article_ids"):
        return list(dict.fromkeys(params["article_ids"]))[:MAX_CLASSIFY_PER_JOB]
    from ..api.records import apply_record_filters  # local import to avoid a cycle
    q = select(Article.id)
    q = apply_record_filters(q, params.get("filters") or {})
    q = q.order_by(Article.published_at.desc().nullslast())
    limit = max(1, min(int(params.get("limit", 100)), MAX_CLASSIFY_PER_JOB))
    return list(db.scalars(q.limit(limit)))


def _llm_reachable(name: str, pcfg: dict) -> tuple[bool, str]:
    """Quick connectivity probe so a job with an unreachable LLM switches to ML at once."""
    try:
        build_provider(name, {**pcfg, "timeout_seconds": min(15, int(pcfg.get("timeout_seconds", 60)))}).list_models()
        return True, ""
    except LLMError as e:
        if e.kind in ("UNAVAILABLE", "TIMEOUT", "AUTH", "CONFIG", "QUOTA"):
            return False, f"{e.kind}: {e}"
        return True, ""  # e.g. model listing not supported – let the real call decide


@handler("classify")
def _classify(ctx: JobContext, params: dict) -> dict:
    provider = params.get("provider")
    reclassify = bool(params.get("reclassify"))
    actor = params.get("actor") or "operator"
    with SessionLocal() as db:
        ids = select_articles_for_classification(db, params)
        ccfg = settings_store.get(db, "classification")
        engine = (params.get("engine") or ccfg.get("engine") or "llm").lower()
        fallback_note = ""
        if engine == "llm":
            try:
                name, pcfg = resolve_provider_config(db, provider)
            except LLMError as e:
                if not ccfg.get("ml_fallback", True):
                    raise
                name, pcfg, engine, fallback_note = "ml", {}, "ml", f"LLM not configured ({e}) – using ML fallback"
            if engine == "llm" and ccfg.get("ml_fallback", True):
                ok, why = _llm_reachable(name, pcfg)
                if not ok:
                    engine, fallback_note = "ml", f"LLM {name} unavailable ({why[:150]}) – using ML fallback"
        if engine == "ml":
            from .ml import model as ml
            try:
                bundle = ml.ensure_model(db)
            except ml.MLUnavailable as e:
                return {"message": f"ML model unavailable: {e}", "_status": "FAILED"}
            name, pcfg, prompt_version = "ml", {"model": bundle["meta"]["version"]}, ml.ML_PROMPT_VERSION
        else:
            prompt_version = PROMPT_VERSION
        concurrency = max(1, min(4, int(ccfg.get("concurrency", 1))))
        if name in ("ollama", "ml"):
            concurrency = 1  # local GPU/CPU (and SQLite writes): sequential is faster and safer
        model = pcfg.get("model")
        if not reclassify:
            # Avoid duplicate calls for unchanged records already classified with this model/prompt.
            done = set(db.scalars(select(Classification.article_id).where(
                Classification.article_id.in_(ids), Classification.is_current.is_(True),
                Classification.provider == name, Classification.model == model,
                Classification.prompt_version == prompt_version)))
            human = set(db.scalars(select(Classification.article_id).where(
                Classification.article_id.in_(ids), Classification.is_current.is_(True), Classification.origin == "HUMAN")))
            skipped = len([i for i in ids if i in done or i in human])
            ids = [i for i in ids if i not in done and i not in human]
        else:
            skipped = 0
        if engine == "ml" and (fallback_note or not reclassify):
            # The ML model fills gaps; it never replaces an existing LLM or human classification unless the
            # operator explicitly reclassifies with the ML engine.
            keep = set(db.scalars(select(Classification.article_id).where(
                Classification.article_id.in_(ids), Classification.is_current.is_(True),
                Classification.status == "VALID", Classification.provider != "ml")))
            skipped += len([i for i in ids if i in keep])
            ids = [i for i in ids if i not in keep]
        for i in range(0, len(ids), 500):
            chunk = ids[i:i + 500]
            for a in db.scalars(select(Article).where(Article.id.in_(chunk))):
                a.classification_status = "QUEUED"
        db.commit()
    total = len(ids)
    ctx.update(total=total, processed=0, succeeded=0, failed=0,
               message=(f"{fallback_note}. " if fallback_note else "") + f"Classifying {total} record(s) with {name}/{model}"
               + (f"; {skipped} already done" if skipped else ""))
    counts = {"ok": 0, "failed": 0, "relevant": 0, "processed": 0, "ml_fallback": 0, "kept": 0}
    state = {"engine": engine}

    def one(aid: str) -> str:
        with SessionLocal() as db:
            art = db.get(Article, aid)
            if art is None:
                return "missing"
            try:
                if state["engine"] == "ml" and engine == "llm" and has_llm_or_human_result(db, art):
                    art.classification_status = "CLASSIFIED"  # keep the existing LLM/human result
                    db.commit()
                    return "kept"
                note = fallback_note or (state.get("note") if state["engine"] == "ml" else None)
                cls = classify_article(db, art, provider_name=None if name == "ml" else name, actor=actor,
                                       engine=state["engine"], note=note)
                db.commit()
                if state["engine"] == "llm" and cls.provider == "ml":
                    state["engine"] = "ml"  # the LLM went down mid-job: do not wait for it on every record
                    state["note"] = f"LLM {name} became unavailable during this job – classified by the ML fallback"
                    counts["ml_fallback"] += 1
                elif cls.provider == "ml" and engine == "llm":
                    counts["ml_fallback"] += 1
                if cls.status == "VALID":
                    return "relevant" if cls.relevance == "RELEVANT" else "ok"
                return "failed"
            except Exception:
                db.rollback()
                log.exception("Classification of %s crashed", aid)
                art = db.get(Article, aid)
                if art is not None:
                    art.classification_status = "CLASSIFIED" if art.current_classification_id else "FAILED"
                    db.commit()
                return "failed"

    cancelled = False
    consecutive_fail = 0
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        pending = list(ids)
        while pending and not cancelled:
            window, pending = pending[:concurrency], pending[concurrency:]
            for fut in as_completed([pool.submit(one, aid) for aid in window]):
                r = fut.result()
                counts["processed"] += 1
                if r == "kept":
                    counts["kept"] += 1
                elif r == "failed":
                    counts["failed"] += 1
                    consecutive_fail += 1
                else:
                    counts["ok"] += 1
                    consecutive_fail = 0
                    if r == "relevant":
                        counts["relevant"] += 1
            ctx.update(processed=counts["processed"], succeeded=counts["ok"], failed=counts["failed"],
                       message=f"{counts['processed']}/{total} processed, {counts['relevant']} relevant, "
                               f"{counts['failed']} failed")
            if ctx.cancelled():
                cancelled = True
            if consecutive_fail >= 10:
                ctx.update(message=f"Stopped after 10 consecutive failures – check the LLM provider. "
                                   f"{counts['processed']}/{total} processed.")
                break
    if pending:
        with SessionLocal() as db:
            for i in range(0, len(pending), 500):
                for a in db.scalars(select(Article).where(Article.id.in_(pending[i:i + 500]))):
                    if a.classification_status == "QUEUED":
                        a.classification_status = "CLASSIFIED" if a.current_classification_id else "UNCLASSIFIED"
            db.commit()
    msg = ((f"{fallback_note}. " if fallback_note else "")
           + f"Processed {counts['processed']} of {total}: {counts['ok']} classified ({counts['relevant']} relevant), "
           f"{counts['failed']} failed" + (f", {skipped} skipped (already classified)" if skipped else "")
           + (f", {counts['ml_fallback']} by the ML fallback after the LLM became unavailable"
              if counts["ml_fallback"] else "")
           + (f", {counts['kept']} kept their existing LLM/human classification" if counts["kept"] else "")
           + (", cancelled" if cancelled else "") + (f", {len(pending)} not processed" if pending else ""))
    status = "FAILED" if counts["failed"] and not counts["ok"] else "COMPLETED"
    return {"message": msg, **counts, "skipped": skipped, "_status": status}


@handler("ml_train")
def _ml_train(ctx: JobContext, params: dict) -> dict:
    from .ml import model as ml
    ctx.update(message="Training the ML classifier (TF-IDF + logistic regression)")
    with SessionLocal() as db:
        try:
            meta = ml.train(db, actor=params.get("actor") or "operator")
        except ml.MLUnavailable as e:
            return {"message": str(e), "_status": "FAILED"}
    rel = meta["metrics"]["relevance"]
    return {"message": f"Trained {meta['version']} on {meta['training_rows']} records; relevance agreement "
                       f"{rel.get('accuracy', 0):.1%} (cross-validated)", "version": meta["version"],
            "_status": "COMPLETED"}


@handler("ollama_pull")
def _ollama_pull(ctx: JobContext, params: dict) -> dict:
    from .ollama_setup import pull_model
    return pull_model(params["base_url"], params["model"], ctx)
