"""In-process background job runner backed by the ``jobs`` table.

Long-running work (imports, fetches, bulk classification, model downloads)
runs in a small bounded thread pool so API requests return immediately.
Progress is persisted so the UI can poll it, and jobs with the same
``dedup_key`` are never queued twice (prevents duplicate scheduled fetches).
"""
from __future__ import annotations

import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Callable

from sqlalchemy import select, update

from ..config import settings
from ..db.models import ImportBatch, Job, utcnow
from ..db.session import SessionLocal
from .text import new_id

log = logging.getLogger(__name__)

ACTIVE = ("QUEUED", "RUNNING")


class JobContext:
    def __init__(self, job_id: str):
        self.job_id = job_id
        self._last_cancel_check = 0

    def update(self, processed: int | None = None, total: int | None = None, succeeded: int | None = None,
               failed: int | None = None, message: str | None = None) -> None:
        vals = {k: v for k, v in dict(processed=processed, total=total, succeeded=succeeded, failed=failed,
                                      message=message).items() if v is not None}
        if not vals:
            return
        with SessionLocal() as db:
            db.execute(update(Job).where(Job.id == self.job_id).values(**vals))
            db.commit()

    def cancelled(self) -> bool:
        if SHUTTING_DOWN.is_set():
            return True
        with SessionLocal() as db:
            return bool(db.scalar(select(Job.cancel_requested).where(Job.id == self.job_id)))


Handler = Callable[[JobContext, dict], dict]
SHUTTING_DOWN = threading.Event()  # set on application shutdown; running jobs stop at the next check
_handlers: dict[str, Handler] = {}


def handler(job_type: str):
    def deco(fn: Handler) -> Handler:
        _handlers[job_type] = fn
        return fn
    return deco


class JobRunner:
    def __init__(self, workers: int):
        self.pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="rdi-job")
        self._lock = threading.Lock()
        self._shutdown = False

    def submit(self, job_type: str, params: dict, actor: str | None = None, dedup_key: str | None = None) -> Job:
        if job_type not in _handlers:
            raise ValueError(f"Unknown job type {job_type}")
        with self._lock, SessionLocal() as db:
            if dedup_key:
                existing = db.scalar(select(Job).where(Job.dedup_key == dedup_key, Job.status.in_(ACTIVE)))
                if existing is not None:
                    return existing
            job = Job(id=new_id("JOB_"), job_type=job_type, status="QUEUED", params=params, created_by=actor,
                      dedup_key=dedup_key, message="Queued")
            db.add(job)
            db.commit()
            db.refresh(job)
        if self._shutdown:
            raise RuntimeError("Job runner is shutting down")
        self.pool.submit(self._run, job.id)
        return job

    def _run(self, job_id: str) -> None:
        with SessionLocal() as db:
            job = db.get(Job, job_id)
            if job is None or job.status != "QUEUED":
                return
            if job.cancel_requested:
                job.status, job.finished_at, job.message = "CANCELLED", utcnow(), "Cancelled before start"
                db.commit()
                return
            job.status, job.started_at, job.message = "RUNNING", utcnow(), "Running"
            db.commit()
            job_type, params = job.job_type, dict(job.params or {})
        ctx = JobContext(job_id)
        try:
            result = _handlers[job_type](ctx, params) or {}
            with SessionLocal() as db:
                job = db.get(Job, job_id)
                job.result = result
                if SHUTTING_DOWN.is_set():
                    job.status = "INTERRUPTED"
                    job.message = (result.get("message") or "") + " - interrupted by application shutdown; re-run it"
                else:
                    job.status = "CANCELLED" if job.cancel_requested else result.get("_status", "COMPLETED")
                job.finished_at = utcnow()
                if result.get("message"):
                    job.message = result["message"]
                db.commit()
        except Exception as e:  # recorded, never crashes the runner
            log.exception("Job %s (%s) failed", job_id, job_type)
            with SessionLocal() as db:
                job = db.get(Job, job_id)
                job.status = "INTERRUPTED" if SHUTTING_DOWN.is_set() else "FAILED"
                job.finished_at = utcnow()
                job.message = f"{type(e).__name__}: {e}"[:1000]
                db.commit()

    def shutdown(self) -> None:
        self._shutdown = True
        SHUTTING_DOWN.set()
        # Give running jobs a few seconds to notice the flag and record their state.
        self.pool.shutdown(wait=False, cancel_futures=True)
        for t in list(getattr(self.pool, "_threads", [])):
            t.join(timeout=8)


_runner: JobRunner | None = None


def runner() -> JobRunner:
    global _runner
    if _runner is None:
        _runner = JobRunner(settings.job_workers)
    return _runner


def recover_interrupted() -> int:
    """Mark jobs/imports left running by a previous process as INTERRUPTED."""
    with SessionLocal() as db:
        n = db.execute(update(Job).where(Job.status.in_(ACTIVE)).values(
            status="INTERRUPTED", finished_at=utcnow(), message="Interrupted by application restart – re-run it"
        )).rowcount
        db.execute(update(ImportBatch).where(ImportBatch.status.in_(("QUEUED", "RUNNING"))).values(
            status="INTERRUPTED", finished_at=utcnow(),
            message="Interrupted by application restart – re-run the import (it is idempotent)"))
        from ..db.models import Article
        stuck = Article.classification_status.in_(("QUEUED", "PROCESSING"))
        db.execute(update(Article).where(stuck, Article.current_classification_id.is_not(None)).values(
            classification_status="CLASSIFIED"))
        db.execute(update(Article).where(stuck).values(classification_status="UNCLASSIFIED"))
        db.commit()
    return n


def shutdown() -> None:
    global _runner
    if _runner is not None:
        _runner.shutdown()
        _runner = None
