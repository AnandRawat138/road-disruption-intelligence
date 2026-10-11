"""Command-line utilities used by the Windows scripts and operators.

    python -m rdi.cli init-db
    python -m rdi.cli data-report
    python -m rdi.cli import-history [--include-legacy]
    python -m rdi.cli status
    python -m rdi.cli backup
    python -m rdi.cli restore <backup-file-name> --yes
    python -m rdi.cli diagnose
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

from sqlalchemy import func, select

from .config import settings
from .db.models import Article, ArticleSighting, Classification, ImportBatch, Incident
from .db.session import SessionLocal, backup_database, init_db, reset_engine
from .logging_setup import configure_logging


def _p(msg: str) -> None:
    print(msg, flush=True)


def cmd_init_db(_a) -> int:
    info = init_db()
    from .services.acquisition import seed_sources
    with SessionLocal() as db:
        seed_sources(db)
    _p(f"Database: {settings.database_url.replace('sqlite:///', '')}")
    _p("Created new database." if info["new_database"] else f"Existing database is at schema v{info['to_version']}.")
    if info.get("backup"):
        _p(f"Backup made before migration: {info['backup']}")
    return 0


def cmd_data_report(_a) -> int:
    from .services import importer
    files = importer.discover_files()
    _p(f"Historical data directory: {settings.historical_data_dir}")
    if not files:
        _p("  (no importable files found)")
    for f in files:
        _p(f"  {f.name:<55} {f.size / 1e6:8.1f} MB  {f.role}")
    return 0


def cmd_import_history(a) -> int:
    from .services import importer
    init_db()
    files = [f for f in importer.discover_files() if a.include_legacy or f.role != "LEGACY_DB"]
    order = {"RAW_ARTICLES": 0, "DEDUPLICATED": 1, "PRIOR_RELEVANT": 2, "WEAK_LABEL_FILE": 3, "EVAL_SPLIT": 4,
             "LEGACY_DB": 5}
    files.sort(key=lambda f: order.get(f.role, 9))
    if not files:
        _p("No historical files found – nothing to import.")
        return 0
    totals = {"discovered": 0, "imported": 0, "duplicate": 0, "invalid": 0, "failed": 0}
    with SessionLocal() as db:
        for f in files:
            _p(f"Importing {f.name} ({f.role}) ...")
            b = importer.create_batch(db, f.path)

            def progress(done, total, msg):
                if done % 5000 == 0:
                    _p(f"    {msg}")
                return True
            b = importer.run_import(db, b.id, progress)
            _p(f"  -> {b.status}: {b.message}")
            for k in totals:
                totals[k] += getattr(b, k)
    _p("Totals: " + ", ".join(f"{k}={v}" for k, v in totals.items()))
    return 0


def cmd_refresh_prefilter(_a) -> int:
    """Recompute keyword pre-filter labels (does not touch classifications)."""
    from .services import prefilter
    init_db()
    changed = 0
    with SessionLocal() as db:
        ids = list(db.scalars(select(Article.id)))
    for i in range(0, len(ids), 500):  # short transactions so the running app is never blocked for long
        with SessionLocal() as db:
            for a in db.scalars(select(Article).where(Article.id.in_(ids[i:i + 500]))):
                extra = a.summary_text if a.summary_text and a.summary_text != a.title else ""
                r = prefilter.assess(a.title, extra)
                if (a.prefilter_label, a.prefilter_reason) != (r.label, r.reason):
                    a.prefilter_label, a.prefilter_score, a.prefilter_reason = r.label, r.score, r.reason
                    changed += 1
            db.commit()
    _p(f"Pre-filter labels updated for {changed} article(s).")
    return 0


def cmd_status(_a) -> int:
    init_db()
    with SessionLocal() as db:
        out = {
            "articles": db.scalar(select(func.count(Article.id))),
            "source_rows": db.scalar(select(func.count(ArticleSighting.id))),
            "classified": db.scalar(select(func.count(Article.id)).where(Article.current_classification_id.is_not(None))),
            "classifications_total": db.scalar(select(func.count(Classification.id))),
            "incidents": db.scalar(select(func.count(Incident.id))),
            "completed_imports": db.scalar(select(func.count(ImportBatch.id)).where(
                ImportBatch.status.in_(("COMPLETED", "COMPLETED_WITH_ERRORS")))),
        }
    print(json.dumps(out))
    return 0


def cmd_imports_done(_a) -> int:
    """Print only the number of completed import batches (used by setup_and_start.bat)."""
    init_db()
    with SessionLocal() as db:
        print(db.scalar(select(func.count(ImportBatch.id)).where(
            ImportBatch.status.in_(("COMPLETED", "COMPLETED_WITH_ERRORS")))) or 0)
    return 0


def cmd_backup(_a) -> int:
    init_db()
    path = backup_database("manual")
    _p(f"Backup written: {path}" if path else "No SQLite database to back up.")
    return 0 if path else 1


def cmd_restore(a) -> int:
    src = (settings.backups_dir / Path(a.name).name).resolve()
    if settings.backups_dir.resolve() not in src.parents or not src.is_file():
        _p(f"Backup not found in {settings.backups_dir}: {a.name}")
        return 1
    if not a.yes:
        _p("Restoring replaces the current database. Stop the application first, then re-run with --yes.")
        return 1
    target = settings.sqlite_path
    if target is None:
        _p("Restore is only supported for the SQLite database.")
        return 1
    pid = settings.runtime_dir / "backend.pid"
    if pid.exists():
        _p("The application appears to be running (runtime/backend.pid exists). Run stop.bat first.")
        return 1
    reset_engine()
    if target.exists():
        safety = backup_database("before_restore")
        _p(f"Current database saved as {safety}")
    for suffix in ("-wal", "-shm"):
        side = target.with_name(target.name + suffix)
        if side.exists():
            side.unlink()
    shutil.copy2(src, target)
    _p(f"Restored {src.name} -> {target}")
    return 0


def cmd_diagnose(_a) -> int:
    import platform
    import socket

    import httpx
    from .services import ollama_setup
    ok = True
    _p(f"Python {platform.python_version()} on {platform.platform()}")
    _p(f"Runtime dir: {settings.runtime_dir}  (writable: {_writable(settings.runtime_dir)})")
    _p(f"Historical data dir: {settings.historical_data_dir}  (exists: {settings.historical_data_dir.is_dir()})")
    _p(f"Frontend build present: {(settings.frontend_dist / 'index.html').is_file()}")
    with socket.socket() as s:
        in_use = s.connect_ex(("127.0.0.1", settings.port)) == 0
    _p(f"Port {settings.port}: {'IN USE' if in_use else 'free'}")
    try:
        info = init_db()
        _p(f"Database OK (schema v{info['to_version']})")
    except Exception as e:
        ok = False
        _p(f"Database ERROR: {e}")
    st = ollama_setup.detect("http://127.0.0.1:11434")
    _p(f"Ollama installed: {st['installed']}, reachable: {st['reachable']}, version: {st['version']}, "
       f"models: {', '.join(m['name'] for m in st['models']) or 'none'}")
    ua = {"User-Agent": "AviralRoadDisruptionIntel/1.0 (diagnostics)"}  # Nominatim rejects anonymous agents
    for name, url in (("Google News RSS", "https://news.google.com/rss"),
                      ("Nominatim", f"{settings.nominatim_url.rstrip('/')}/status?format=json"),
                      ("Map tiles", "https://tiles.openfreemap.org/styles/positron")):
        try:
            r = httpx.get(url, timeout=8, follow_redirects=True, headers=ua)
            _p(f"Internet check {name}: HTTP {r.status_code}")
        except httpx.HTTPError as e:
            _p(f"Internet check {name}: FAILED ({type(e).__name__})")
    return 0 if ok else 1


def _writable(p: Path) -> bool:
    try:
        p.mkdir(parents=True, exist_ok=True)
        t = p / ".write_test"
        t.write_text("x")
        t.unlink()
        return True
    except OSError:
        return False


def main(argv: list[str] | None = None) -> int:
    configure_logging()
    ap = argparse.ArgumentParser(prog="rdi")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init-db").set_defaults(fn=cmd_init_db)
    sub.add_parser("data-report").set_defaults(fn=cmd_data_report)
    p = sub.add_parser("import-history")
    p.add_argument("--include-legacy", action="store_true", help="also import articles from backend/roaddb.db")
    p.set_defaults(fn=cmd_import_history)
    sub.add_parser("status").set_defaults(fn=cmd_status)
    sub.add_parser("refresh-prefilter").set_defaults(fn=cmd_refresh_prefilter)
    sub.add_parser("imports-done").set_defaults(fn=cmd_imports_done)
    sub.add_parser("backup").set_defaults(fn=cmd_backup)
    p = sub.add_parser("restore")
    p.add_argument("name")
    p.add_argument("--yes", action="store_true")
    p.set_defaults(fn=cmd_restore)
    sub.add_parser("diagnose").set_defaults(fn=cmd_diagnose)
    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
