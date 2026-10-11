"""Polling scheduler for enabled sources.

Only one application instance may run the scheduler: an exclusive lock file in
the runtime directory guarantees that a second instance never schedules
duplicate fetches. Due sources are submitted as jobs with a dedup key, so a
fetch is never queued twice even if a run is slow.
"""
from __future__ import annotations

import logging
import os
import threading
from datetime import timedelta

from sqlalchemy import or_, select

from ..config import settings
from ..db.models import Source, utcnow
from ..db.session import SessionLocal
from .jobs import runner

log = logging.getLogger(__name__)
TICK_SECONDS = 30

_stop = threading.Event()
_thread: threading.Thread | None = None
_lock_fh = None
state = {"running": False, "reason": None, "last_tick": None}


def _acquire_lock() -> bool:
    global _lock_fh
    path = settings.runtime_dir / "scheduler.lock"
    try:
        _lock_fh = open(path, "a+")
        if os.name == "nt":
            import msvcrt
            _lock_fh.seek(0)
            msvcrt.locking(_lock_fh.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(_lock_fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True
    except OSError:
        if _lock_fh:
            _lock_fh.close()
        _lock_fh = None
        return False


def tick() -> list[str]:
    submitted = []
    now = utcnow()
    with SessionLocal() as db:
        due = db.scalars(select(Source).where(Source.enabled.is_(True),
                                              or_(Source.next_run_at.is_(None), Source.next_run_at <= now))).all()
        for s in due:
            if s.next_run_at is None:
                # first start: wait a minute after boot so startup stays responsive
                s.next_run_at = now + timedelta(minutes=1)
                continue
            runner().submit("fetch_source", {"source_id": s.id, "trigger": "SCHEDULED"}, actor="scheduler",
                            dedup_key=f"fetch:{s.id}")
            submitted.append(s.id)
            # Provisional next run; run_source sets the real value when it finishes.
            s.next_run_at = now + timedelta(minutes=max(30, s.poll_interval_minutes or 180))
        db.commit()
    state["last_tick"] = now
    return submitted


def _loop() -> None:
    while not _stop.wait(TICK_SECONDS):
        try:
            tick()
        except Exception:
            log.exception("Scheduler tick failed")


def start() -> None:
    global _thread
    if not settings.scheduler_enabled:
        state.update(running=False, reason="Disabled by SCHEDULER_ENABLED=false")
        return
    if not _acquire_lock():
        state.update(running=False, reason="Another instance holds the scheduler lock")
        log.warning("Scheduler not started: another instance is running")
        return
    _stop.clear()
    _thread = threading.Thread(target=_loop, name="rdi-scheduler", daemon=True)
    _thread.start()
    state.update(running=True, reason=None)


def stop() -> None:
    global _lock_fh
    _stop.set()
    state["running"] = False
    if _lock_fh:
        try:
            _lock_fh.close()
        except OSError:
            pass
        _lock_fh = None
