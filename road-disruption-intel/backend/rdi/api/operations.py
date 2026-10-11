"""Operational endpoints: sources & acquisition, data import, jobs, alerts, audit log."""
from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import settings
from ..db.models import Alert, AuditLog, FetchRun, ImportBatch, ImportRowError, Job, Source, utcnow
from ..db.session import get_db
from ..services import audit, importer, scheduler, settings_store
from ..services.acquisition import connector_for, source_view
from ..services.connectors import CONNECTORS, ConnectorError
from ..services.jobs import runner
from .common import Page, actor_from, iso, page_envelope, row_dict

router = APIRouter(tags=["operations"])


# ----------------------------------------------------------------------------- sources
@router.get("/api/sources")
def list_sources(db: Session = Depends(get_db)):
    return {"sources": [source_view(db, s) for s in db.scalars(select(Source).order_by(Source.name))],
            "scheduler": {**scheduler.state, "last_tick": iso(scheduler.state.get("last_tick"))},
            "connector_types": [{"type": k, "name": c.display_name, "description": c.description,
                                 "access_notes": c.access_notes, "required_secrets": c.required_secrets}
                                for k, c in CONNECTORS.items()]}


class SourceUpdate(BaseModel):
    enabled: bool | None = None
    name: str | None = Field(default=None, max_length=120)
    poll_interval_minutes: int | None = Field(default=None, ge=15, le=7 * 24 * 60)
    max_records: int | None = Field(default=None, ge=1, le=1000)
    timeout_seconds: int | None = Field(default=None, ge=3, le=120)
    max_retries: int | None = Field(default=None, ge=0, le=6)
    config: dict | None = None


def _validate_config(connector_type: str, cfg: dict) -> dict:
    clean: dict = {}
    for k, v in cfg.items():
        if k.startswith("_"):
            continue
        if isinstance(v, list):
            v = [str(x).strip()[:300] for x in v if str(x).strip()][:200]
        elif isinstance(v, str):
            v = v.strip()[:1000]
        elif not isinstance(v, (int, float, bool)) and v is not None:
            raise HTTPException(422, f"Invalid value for {k}")
        clean[k] = v
    if connector_type == "custom_rss":
        for url in clean.get("feeds", []):
            if not url.startswith(("http://", "https://")):
                raise HTTPException(422, f"Feed URL must start with http(s)://: {url}")
    if "queries_per_run" in clean:
        clean["queries_per_run"] = max(1, min(50, int(clean["queries_per_run"])))
    if "request_spacing_seconds" in clean:
        floor = 6 if connector_type == "gdelt_doc" else 1
        clean["request_spacing_seconds"] = max(floor, min(60, float(clean["request_spacing_seconds"])))
    return clean


@router.patch("/api/sources/{source_id}")
def update_source(source_id: str, body: SourceUpdate, db: Session = Depends(get_db), actor: str = Depends(actor_from)):
    s = db.get(Source, source_id)
    if s is None:
        raise HTTPException(404, "Source not found")
    min_poll = int(settings_store.get(db, "acquisition").get("min_poll_minutes", 30))
    changes = body.model_dump(exclude_none=True)
    if "poll_interval_minutes" in changes and changes["poll_interval_minutes"] < min_poll:
        raise HTTPException(422, f"Polling interval must be at least {min_poll} minutes to respect provider limits")
    if "config" in changes:
        cursor = (s.config or {}).get("_cursor")
        new_cfg = {**(s.config or {}), **_validate_config(s.connector_type, changes.pop("config"))}
        if cursor is not None:
            new_cfg["_cursor"] = cursor
        s.config = new_cfg
    for k, v in changes.items():
        setattr(s, k, v)
    if body.enabled:
        s.next_run_at = s.next_run_at or utcnow()
    audit.record(db, "source", s.id, "updated", actor, changes={k: v for k, v in body.model_dump(exclude_none=True).items()})
    db.commit()
    return source_view(db, s)


@router.post("/api/sources/{source_id}/fetch")
def fetch_now(source_id: str, db: Session = Depends(get_db), actor: str = Depends(actor_from)):
    s = db.get(Source, source_id)
    if s is None:
        raise HTTPException(404, "Source not found")
    job = runner().submit("fetch_source", {"source_id": s.id, "trigger": "MANUAL"}, actor, dedup_key=f"fetch:{s.id}")
    return {"job_id": job.id, "status": job.status}


@router.post("/api/sources/{source_id}/test")
def test_source(source_id: str, db: Session = Depends(get_db)):
    """Real connectivity test: fetch up to 3 items without storing them."""
    s = db.get(Source, source_id)
    if s is None:
        raise HTTPException(404, "Source not found")
    conn = connector_for(s)
    status, msg = conn.configuration_status()
    if status != "CONFIGURED":
        return {"ok": False, "status": status, "message": msg, "sample": []}
    if hasattr(conn, "cfg"):
        conn.cfg["queries_per_run"] = 1
    try:
        res = conn.fetch(3)
    except ConnectorError as e:
        return {"ok": False, "status": e.kind, "message": str(e), "sample": []}
    except Exception as e:  # pragma: no cover - defensive
        return {"ok": False, "status": "ERROR", "message": f"{type(e).__name__}: {e}", "sample": []}
    ok = bool(res.items) or not res.errors
    return {"ok": ok, "status": "OK" if ok else "ERROR",
            "message": (f"Received {len(res.items)} item(s) from {res.requests} request(s)."
                        + (f" Errors: {'; '.join(res.errors[:2])}" if res.errors else "")),
            "sample": [{"title": i.title, "url": i.url, "source": i.source_name,
                        "published_at": iso(i.published_at)} for i in res.items[:3]]}


@router.get("/api/sources/{source_id}/runs")
def source_runs(source_id: str, page: Page = Depends(), db: Session = Depends(get_db)):
    total = db.scalar(select(func.count(FetchRun.id)).where(FetchRun.source_id == source_id)) or 0
    runs = db.scalars(select(FetchRun).where(FetchRun.source_id == source_id).order_by(FetchRun.started_at.desc())
                      .offset(page.offset).limit(page.page_size)).all()
    return page_envelope([row_dict(r) for r in runs], total, page)


# ----------------------------------------------------------------------------- imports
_row_count_cache: dict[tuple, int | None] = {}


@router.get("/api/imports/files")
def import_files(db: Session = Depends(get_db)):
    history = importer.import_history(db)
    out = []
    for f in importer.discover_files():
        st = f.path.stat()
        key = (str(f.path), st.st_mtime, st.st_size)
        if key not in _row_count_cache:
            _row_count_cache[key] = importer.count_rows(f.path)
        last = db.scalars(select(ImportBatch).where(ImportBatch.file_path == str(f.path))
                          .order_by(ImportBatch.created_at.desc()).limit(1)).first()
        out.append({"path": str(f.path), "name": f.name, "size_bytes": f.size, "format": f.fmt, "role": f.role,
                    "role_description": f.role_description, "rows": _row_count_cache[key],
                    "modified_at": iso(datetime.fromtimestamp(st.st_mtime, timezone.utc).replace(tzinfo=None)),
                    "previously_imported": str(f.path) in history,
                    "last_batch": {"id": last.id, "status": last.status, "finished_at": iso(last.finished_at),
                                   "message": last.message} if last else None})
    return {"data_dir": str(settings.historical_data_dir), "data_dir_exists": settings.historical_data_dir.is_dir(),
            "files": out,
            "recommended_order": ["RAW_ARTICLES", "DEDUPLICATED", "PRIOR_RELEVANT", "WEAK_LABEL_FILE", "EVAL_SPLIT",
                                  "LEGACY_DB"]}


class ImportRequest(BaseModel):
    paths: list[str] = Field(min_length=1, max_length=50)


ROLE_ORDER = {"RAW_ARTICLES": 0, "DEDUPLICATED": 1, "PRIOR_RELEVANT": 2, "WEAK_LABEL_FILE": 3, "EVAL_SPLIT": 4,
              "LEGACY_DB": 5, "GENERIC": 6}


@router.post("/api/imports/run")
def run_imports(body: ImportRequest, db: Session = Depends(get_db), actor: str = Depends(actor_from)):
    paths = []
    for p in body.paths:
        try:
            paths.append(importer.resolve_safe(p))
        except (PermissionError, ValueError, FileNotFoundError) as e:
            raise HTTPException(400, f"{Path(p).name}: {e}") from e
    paths.sort(key=lambda p: ROLE_ORDER.get(importer.detect_role(p)[0], 9))
    batches = []
    for p in paths:
        b = importer.create_batch(db, p)
        job = runner().submit("import", {"batch_id": b.id}, actor, dedup_key=f"import:{p}")
        b.job_id = job.id
        db.commit()
        batches.append({"batch_id": b.id, "job_id": job.id, "file": b.file_name})
    return {"batches": batches}


@router.post("/api/imports/upload")
async def upload_import(file: UploadFile = File(...), db: Session = Depends(get_db), actor: str = Depends(actor_from)):
    try:
        safe = importer.sanitize_upload_name(file.filename or "")
    except ValueError as e:
        raise HTTPException(415, str(e)) from e
    settings.uploads_dir.mkdir(parents=True, exist_ok=True)
    stamp = utcnow().strftime("%Y%m%d_%H%M%S")
    target = (settings.uploads_dir / f"{stamp}_{safe}").resolve()
    if settings.uploads_dir.resolve() not in target.parents:
        raise HTTPException(400, "Invalid file name")
    limit = settings.max_upload_mb * 1024 * 1024
    size = 0
    with open(target, "wb") as out:
        while chunk := await file.read(1024 * 1024):
            size += len(chunk)
            if size > limit:
                out.close()
                os.remove(target)
                raise HTTPException(413, f"File exceeds {settings.max_upload_mb} MB")
            out.write(chunk)
    with open(target, "rb") as fh:
        head = fh.read(4096)
    if b"\x00" in head:
        os.remove(target)
        raise HTTPException(415, "File looks binary; only text JSON/JSONL/CSV is accepted")
    b = importer.create_batch(db, target)
    job = runner().submit("import", {"batch_id": b.id}, actor)
    b.job_id = job.id
    db.commit()
    return {"batch_id": b.id, "job_id": job.id, "file": safe, "size_bytes": size}


@router.get("/api/imports/batches")
def list_batches(page: Page = Depends(), db: Session = Depends(get_db)):
    total = db.scalar(select(func.count(ImportBatch.id))) or 0
    rows = db.scalars(select(ImportBatch).order_by(ImportBatch.created_at.desc()).offset(page.offset).limit(page.page_size)).all()
    items = []
    for b in rows:
        d = row_dict(b)
        d["file_path"] = b.file_name if settings.uploads_dir.resolve() in Path(b.file_path).resolve().parents else b.file_path
        d["error_rows"] = db.scalar(select(func.count(ImportRowError.id)).where(ImportRowError.batch_id == b.id)) or 0
        items.append(d)
    return page_envelope(items, total, page)


@router.get("/api/imports/batches/{batch_id}/errors.csv")
def batch_errors(batch_id: str, db: Session = Depends(get_db)):
    if db.get(ImportBatch, batch_id) is None:
        raise HTTPException(404, "Batch not found")
    return PlainTextResponse(importer.error_report_csv(db, batch_id), media_type="text/csv",
                             headers={"Content-Disposition": f'attachment; filename="{batch_id}_errors.csv"'})


# ----------------------------------------------------------------------------- jobs
@router.get("/api/jobs")
def list_jobs(page: Page = Depends(), job_type: str | None = None, active: bool = False, db: Session = Depends(get_db)):
    q = select(Job)
    cq = select(func.count(Job.id))
    if job_type:
        q, cq = q.where(Job.job_type == job_type), cq.where(Job.job_type == job_type)
    if active:
        q, cq = q.where(Job.status.in_(("QUEUED", "RUNNING"))), cq.where(Job.status.in_(("QUEUED", "RUNNING")))
    total = db.scalar(cq) or 0
    rows = db.scalars(q.order_by(Job.created_at.desc()).offset(page.offset).limit(page.page_size)).all()
    return page_envelope([row_dict(j) for j in rows], total, page)


@router.get("/api/jobs/{job_id}")
def get_job(job_id: str, db: Session = Depends(get_db)):
    j = db.get(Job, job_id)
    if j is None:
        raise HTTPException(404, "Job not found")
    return row_dict(j)


@router.post("/api/jobs/{job_id}/cancel")
def cancel_job(job_id: str, db: Session = Depends(get_db), actor: str = Depends(actor_from)):
    j = db.get(Job, job_id)
    if j is None:
        raise HTTPException(404, "Job not found")
    if j.status not in ("QUEUED", "RUNNING"):
        raise HTTPException(409, f"Job is already {j.status}")
    j.cancel_requested = True
    audit.record(db, "job", j.id, "cancel_requested", actor)
    db.commit()
    return {"id": j.id, "cancel_requested": True}


# ----------------------------------------------------------------------------- alerts & audit
@router.get("/api/alerts")
def list_alerts(unread_only: bool = False, db: Session = Depends(get_db)):
    q = select(Alert)
    if unread_only:
        q = q.where(Alert.read_at.is_(None))
    rows = db.scalars(q.order_by(Alert.created_at.desc()).limit(100)).all()
    return {"items": [row_dict(a) for a in rows],
            "unread": db.scalar(select(func.count(Alert.id)).where(Alert.read_at.is_(None))) or 0}


@router.post("/api/alerts/read-all")
def read_all_alerts(db: Session = Depends(get_db)):
    for a in db.scalars(select(Alert).where(Alert.read_at.is_(None))):
        a.read_at = utcnow()
    db.commit()
    return {"ok": True}


@router.post("/api/alerts/{alert_id}/read")
def read_alert(alert_id: int, db: Session = Depends(get_db)):
    a = db.get(Alert, alert_id)
    if a is None:
        raise HTTPException(404, "Alert not found")
    a.read_at = a.read_at or utcnow()
    db.commit()
    return {"ok": True}


@router.get("/api/audit")
def audit_log(page: Page = Depends(), entity_type: str | None = None, entity_id: str | None = None,
              db: Session = Depends(get_db)):
    q, cq = select(AuditLog), select(func.count(AuditLog.id))
    if entity_type:
        q, cq = q.where(AuditLog.entity_type == entity_type), cq.where(AuditLog.entity_type == entity_type)
    if entity_id:
        q, cq = q.where(AuditLog.entity_id == entity_id), cq.where(AuditLog.entity_id == entity_id)
    total = db.scalar(cq) or 0
    rows = db.scalars(q.order_by(AuditLog.at.desc()).offset(page.offset).limit(page.page_size)).all()
    return page_envelope([row_dict(r) for r in rows], total, page)
