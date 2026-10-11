"""Background job implementations (registered with the job runner on import)."""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

from sqlalchemy import select

from ..db.models import Article, Classification
from ..db.session import SessionLocal
from . import importer, settings_store
from .acquisition import run_source
from .classification.classifier import classify_article, resolve_provider_config
from .classification.schema import PROMPT_VERSION
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


@handler("classify")
def _classify(ctx: JobContext, params: dict) -> dict:
    provider = params.get("provider")
    reclassify = bool(params.get("reclassify"))
    actor = params.get("actor") or "operator"
    with SessionLocal() as db:
        ids = select_articles_for_classification(db, params)
        name, pcfg = resolve_provider_config(db, provider)
        concurrency = max(1, min(4, int(settings_store.get(db, "classification").get("concurrency", 1))))
        if name == "ollama":
            concurrency = 1  # local GPU/CPU: sequential is faster and safer
        model = pcfg.get("model")
        if not reclassify:
            # Avoid duplicate LLM calls for unchanged records already classified with this model/prompt.
            done = set(db.scalars(select(Classification.article_id).where(
                Classification.article_id.in_(ids), Classification.is_current.is_(True),
                Classification.provider == name, Classification.model == model,
                Classification.prompt_version == PROMPT_VERSION)))
            human = set(db.scalars(select(Classification.article_id).where(
                Classification.article_id.in_(ids), Classification.is_current.is_(True), Classification.origin == "HUMAN")))
            skipped = len([i for i in ids if i in done or i in human])
            ids = [i for i in ids if i not in done and i not in human]
        else:
            skipped = 0
        for i in range(0, len(ids), 500):
            chunk = ids[i:i + 500]
            for a in db.scalars(select(Article).where(Article.id.in_(chunk))):
                a.classification_status = "QUEUED"
        db.commit()
    total = len(ids)
    ctx.update(total=total, processed=0, succeeded=0, failed=0,
               message=f"Classifying {total} record(s) with {name}/{model}" + (f"; {skipped} already done" if skipped else ""))
    counts = {"ok": 0, "failed": 0, "relevant": 0, "processed": 0}

    def one(aid: str) -> str:
        with SessionLocal() as db:
            art = db.get(Article, aid)
            if art is None:
                return "missing"
            try:
                cls = classify_article(db, art, provider_name=name, actor=actor)
                db.commit()
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
                if r == "failed":
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
    msg = (f"Processed {counts['processed']} of {total}: {counts['ok']} classified ({counts['relevant']} relevant), "
           f"{counts['failed']} failed" + (f", {skipped} skipped (already classified)" if skipped else "")
           + (", cancelled" if cancelled else "") + (f", {len(pending)} not processed" if pending else ""))
    status = "FAILED" if counts["failed"] and not counts["ok"] else "COMPLETED"
    return {"message": msg, **counts, "skipped": skipped, "_status": status}


@handler("ollama_pull")
def _ollama_pull(ctx: JobContext, params: dict) -> dict:
    from .ollama_setup import pull_model
    return pull_model(params["base_url"], params["model"], ctx)
