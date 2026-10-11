"""Engine/session management, safe schema initialisation and backups."""
from __future__ import annotations

import logging
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Iterator

from sqlalchemy import create_engine, event, inspect, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from ..config import settings
from .models import Base, SchemaVersion

log = logging.getLogger(__name__)

# Bump when the schema changes and add a migration function to MIGRATIONS.
SCHEMA_VERSION = 1
MIGRATIONS: dict[int, callable] = {}

_engine: Engine | None = None
_SessionLocal: sessionmaker | None = None


def _make_engine(url: str) -> Engine:
    kwargs = {"future": True, "pool_pre_ping": True}
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False, "timeout": 30}
    eng = create_engine(url, **kwargs)
    if url.startswith("sqlite"):
        @event.listens_for(eng, "connect")
        def _sqlite_pragmas(dbapi_conn, _):  # noqa: ANN001
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA journal_mode=WAL")
            cur.execute("PRAGMA synchronous=NORMAL")
            cur.execute("PRAGMA foreign_keys=ON")
            cur.execute("PRAGMA busy_timeout=30000")
            cur.close()
    return eng


def get_engine() -> Engine:
    global _engine, _SessionLocal
    if _engine is None:
        settings.ensure_dirs()
        _engine = _make_engine(settings.database_url)
        _SessionLocal = sessionmaker(bind=_engine, autoflush=False, expire_on_commit=False, future=True)
    return _engine


def reset_engine() -> None:
    """Dispose the engine (tests / restore)."""
    global _engine, _SessionLocal
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _SessionLocal = None


def SessionLocal() -> Session:  # noqa: N802 - factory name kept for readability
    get_engine()
    assert _SessionLocal is not None
    return _SessionLocal()


@contextmanager
def session_scope() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def get_db() -> Iterator[Session]:
    """FastAPI dependency."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def backup_database(reason: str = "manual") -> Path | None:
    """Create a consistent copy of the SQLite database using the backup API."""
    path = settings.sqlite_path
    if path is None or not path.exists():
        return None
    settings.backups_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_reason = "".join(ch for ch in reason if ch.isalnum() or ch in "-_")[:40] or "backup"
    target = settings.backups_dir / f"rdi_{stamp}_{safe_reason}.db"
    src = sqlite3.connect(str(path))
    dst = sqlite3.connect(str(target))
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()
    log.info("Database backup written to %s", target.name)
    return target


def init_db() -> dict:
    """Create tables for a new database or migrate an existing one.

    Existing databases are backed up before any migration is applied.
    """
    eng = get_engine()
    insp = inspect(eng)
    existing_tables = set(insp.get_table_names())
    is_new = "schema_version" not in existing_tables
    current = 0
    if not is_new:
        with Session(eng) as s:
            current = s.scalar(select(SchemaVersion.version).order_by(SchemaVersion.version.desc())) or 0

    info = {"new_database": is_new, "from_version": current, "to_version": SCHEMA_VERSION, "backup": None}
    if not is_new and current < SCHEMA_VERSION:
        backup = backup_database(f"pre_migration_v{current}_to_v{SCHEMA_VERSION}")
        info["backup"] = str(backup) if backup else None
        for v in range(current + 1, SCHEMA_VERSION + 1):
            fn = MIGRATIONS.get(v)
            if fn:
                log.info("Applying migration to schema v%s", v)
                fn(eng)

    # create_all only creates missing tables/indexes; it never drops data.
    Base.metadata.create_all(eng)
    if is_new or current < SCHEMA_VERSION:
        with Session(eng) as s:
            s.add(SchemaVersion(version=SCHEMA_VERSION, note="initial" if is_new else "migrated"))
            s.commit()
    return info
