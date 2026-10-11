"""Running source connectors, recording fetch runs and maintaining source health."""
from __future__ import annotations

import logging
from datetime import timedelta

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db.models import Article, FetchRun, Source, utcnow
from . import settings_store
from .connectors import CONNECTORS, DEFAULT_SOURCES, ConnectorError
from .ingest import Ingestor

log = logging.getLogger(__name__)


def seed_sources(db: Session) -> None:
    for spec in DEFAULT_SOURCES:
        if db.get(Source, spec["id"]) is None:
            cls = CONNECTORS[spec["connector_type"]]
            db.add(Source(config=dict(cls.default_config), **spec))
    db.commit()


def connector_for(source: Source, client: httpx.Client | None = None, sleep=None):
    cls = CONNECTORS.get(source.connector_type)
    if cls is None:
        raise ConnectorError("NOT_CONFIGURED", f"Unknown connector type {source.connector_type}")
    return cls(source, client, sleep) if sleep else cls(source, client)


def _iso(dt):
    """UTC ISO-8601 with 'Z' so browsers do not misread naive timestamps as local time."""
    return dt.replace(microsecond=0).isoformat() + "Z" if dt else None


def source_view(db: Session, s: Source) -> dict:
    conn_cls = CONNECTORS.get(s.connector_type)
    try:
        cfg_status, cfg_msg = connector_for(s).configuration_status()
    except Exception as e:  # pragma: no cover - defensive
        cfg_status, cfg_msg = "NOT_CONFIGURED", str(e)
    if s.last_success_at is None and s.last_attempt_at is None:
        verification = "UNVERIFIED"
    elif s.last_status in ("OK", "PARTIAL"):
        verification = "VERIFIED"
    else:
        verification = "FAILING"
    return {
        "id": s.id, "name": s.name, "connector_type": s.connector_type,
        "connector_name": conn_cls.display_name if conn_cls else s.connector_type,
        "description": conn_cls.description if conn_cls else "", "access_notes": conn_cls.access_notes if conn_cls else "",
        "required_secrets": conn_cls.required_secrets if conn_cls else [],
        "enabled": s.enabled, "config": {k: v for k, v in (s.config or {}).items() if not k.startswith("_")},
        "poll_interval_minutes": s.poll_interval_minutes, "max_records": s.max_records,
        "timeout_seconds": s.timeout_seconds, "max_retries": s.max_retries,
        "configuration_status": cfg_status, "configuration_message": cfg_msg, "verification": verification,
        "last_attempt_at": _iso(s.last_attempt_at), "last_success_at": _iso(s.last_success_at), "last_status": s.last_status,
        "last_error": s.last_error, "consecutive_failures": s.consecutive_failures,
        "total_fetched": s.total_fetched, "total_new": s.total_new, "total_duplicates": s.total_duplicates,
        "total_relevant": s.total_relevant, "next_run_at": _iso(s.next_run_at) if s.enabled else None,
    }


def run_source(db: Session, source_id: str, trigger: str = "MANUAL", client: httpx.Client | None = None,
               sleep=None) -> FetchRun:
    source = db.get(Source, source_id)
    if source is None:
        raise ValueError(f"Unknown source {source_id}")
    run = FetchRun(source_id=source.id, trigger=trigger, status="RUNNING")
    db.add(run)
    source.last_attempt_at = utcnow()
    db.commit()
    new_ids: list[str] = []
    try:
        conn = connector_for(source, client, sleep)
        cfg_status, cfg_msg = conn.configuration_status()
        if cfg_status != "CONFIGURED":
            raise ConnectorError("NOT_CONFIGURED", cfg_msg)
        result = conn.fetch(max(1, min(1000, source.max_records or 50)))
        ing = Ingestor(db, "CONNECTOR", source.id, batch_id=f"RUN_{run.id}")
        for item in result.items:
            try:
                with db.begin_nested():
                    out = ing.ingest(item)
                    db.flush()
            except Exception as e:
                log.warning("Ingest failed for item from %s: %s", source.id, e)
                run.invalid += 1
                continue
            run.fetched += 1
            if out.status == "NEW":
                run.new += 1
                new_ids.append(out.article_id)
                if out.prefilter_label == "LIKELY_RELEVANT":
                    run.relevant += 1
            elif out.status == "DUPLICATE":
                run.duplicates += 1
            else:
                run.invalid += 1
        if result.state_updates:
            source.config = {**(source.config or {}), **result.state_updates}
        run.details = {"requests": result.requests, "errors": result.errors[:20], "notes": result.notes}
        if result.errors and not result.items:
            run.status = "ERROR"
            run.error = "; ".join(result.errors[:3])[:2000]
        elif result.errors or result.partial:
            run.status = "PARTIAL"
            run.error = "; ".join(result.errors[:3])[:2000]
        else:
            run.status = "OK"
        if any("RATE" in e.upper() or "429" in e for e in result.errors) and run.status == "ERROR":
            run.status = "RATE_LIMITED"
    except ConnectorError as e:
        run.status = {"NOT_CONFIGURED": "NOT_CONFIGURED", "AUTH": "AUTH_FAILED",
                      "RATE_LIMITED": "RATE_LIMITED"}.get(e.kind, "ERROR")
        run.error = str(e)[:2000]
    except Exception as e:  # a broken connector must never take down the others
        log.exception("Connector %s crashed", source.id)
        run.status, run.error = "ERROR", f"{type(e).__name__}: {e}"[:2000]

    run.finished_at = utcnow()
    source.last_status = run.status
    source.total_fetched += run.fetched
    source.total_new += run.new
    source.total_duplicates += run.duplicates
    source.total_relevant += run.relevant
    if run.status in ("OK", "PARTIAL"):
        source.last_success_at = run.finished_at
        source.consecutive_failures = 0
        source.last_error = run.error
    else:
        source.consecutive_failures += 1
        source.last_error = run.error
    acq = settings_store.get(db, "acquisition")
    interval = max(int(acq.get("min_poll_minutes", 30)), int(source.poll_interval_minutes or 180))
    if run.status in ("AUTH_FAILED", "NOT_CONFIGURED"):
        interval = max(interval, 24 * 60)  # do not hammer a permanently failing source
    elif source.consecutive_failures:
        interval = min(24 * 60, interval * (2 ** min(source.consecutive_failures, 4)))
    source.next_run_at = utcnow() + timedelta(minutes=interval)
    db.commit()
    log.info("Fetch %s [%s]: status=%s fetched=%s new=%s dup=%s", source.id, trigger, run.status, run.fetched,
             run.new, run.duplicates)

    if new_ids:
        _maybe_auto_classify(db, new_ids)
    return run


def _maybe_auto_classify(db: Session, article_ids: list[str]) -> None:
    ccfg = settings_store.get(db, "classification")
    if not ccfg.get("auto_classify_new"):
        return
    min_label = ccfg.get("auto_classify_min_prefilter", "LIKELY_RELEVANT")
    allowed = {"LIKELY_RELEVANT"} if min_label == "LIKELY_RELEVANT" else {"LIKELY_RELEVANT", "POSSIBLY_RELEVANT"}
    ids = list(db.scalars(select(Article.id).where(Article.id.in_(article_ids), Article.prefilter_label.in_(allowed))))
    if ids:
        from .jobs import runner
        runner().submit("classify", {"article_ids": ids, "reclassify": False}, actor="auto-classify")
