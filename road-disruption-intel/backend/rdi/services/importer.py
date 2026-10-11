"""Historical data import (JSONL, JSON, CSV and the legacy v0 SQLite database).

Source files are opened read-only and are never modified. Every import is
recorded as an ``ImportBatch`` with real counts and a per-row error log that
can be downloaded as CSV.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import logging
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterator

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import BACKEND_DIR, settings
from ..db.models import ImportBatch, ImportRowError, utcnow
from . import text
from .ingest import ArticleIn, Ingestor

log = logging.getLogger(__name__)

ALLOWED_EXTENSIONS = {".jsonl", ".ndjson", ".json", ".csv", ".db", ".sqlite"}
MAX_ROW_ERRORS = 5000
COMMIT_EVERY = 500
MAX_JSON_ARRAY_BYTES = 300 * 1024 * 1024

FIELD_ALIASES = {
    "title": ["title", "headline", "name"],
    "url": ["source_url", "url", "link", "article_url"],
    "original_url": ["original_url"],
    "summary": ["description", "summary", "snippet"],
    "text": ["article_text", "content", "text", "body"],
    "source": ["source", "source_name", "publisher", "domain"],
    "source_type": ["source_type"],
    "published": ["publication_time", "published_at", "published", "pubDate", "date", "seendate"],
    "retrieved": ["retrieval_time", "retrieved_at", "collected_at"],
    "language": ["language", "lang"],
    "query": ["query_used", "query"],
    "city": ["city"],
    "external_id": ["article_id", "id", "external_id"],
}


@dataclass
class FileInfo:
    path: Path
    name: str
    size: int
    fmt: str
    role: str
    role_description: str


ROLE_RULES = [
    (r"raw", "RAW_ARTICLES", "Raw collected articles (all fetched rows, including repeats)"),
    (r"dedup", "DEDUPLICATED", "Articles with earlier deduplication flags"),
    (r"relevant", "PRIOR_RELEVANT", "Articles marked relevant by an earlier keyword rule"),
    (r"weak_label", "WEAK_LABEL_FILE", "Earlier 'weak label' file – contains no event labels, only a constant confidence"),
    (r"(dev|val|test)_split", "EVAL_SPLIT", "Earlier evaluation split (subset of relevant articles)"),
    (r"roaddb", "LEGACY_DB", "Legacy v0 application database (articles table)"),
]


def detect_role(path: Path) -> tuple[str, str]:
    low = path.name.lower()
    for pattern, role, desc in ROLE_RULES:
        if re.search(pattern, low):
            return role, desc
    return "GENERIC", "Generic article file"


def file_format(path: Path) -> str:
    ext = path.suffix.lower()
    if ext in (".jsonl", ".ndjson"):
        return "jsonl"
    if ext == ".json":
        return "json"
    if ext == ".csv":
        return "csv"
    if ext in (".db", ".sqlite"):
        return "sqlite"
    return "unknown"


def legacy_db_path() -> Path:
    """The v0 application database (articles only are importable)."""
    return (BACKEND_DIR / "roaddb.db").resolve()


def allowed_roots() -> list[Path]:
    return [settings.historical_data_dir.resolve(), settings.uploads_dir.resolve()]


def _is_allowed(p: Path) -> bool:
    if p == legacy_db_path():
        return True
    return any(p == r or r in p.parents for r in allowed_roots())


def resolve_safe(path_str: str) -> Path:
    """Resolve a user-supplied path and ensure it is inside an allowed root."""
    p = Path(path_str)
    if not p.is_absolute():
        p = settings.historical_data_dir / p
    p = p.resolve()
    if not _is_allowed(p):
        raise PermissionError("Path is outside the allowed import directories")
    if p.suffix.lower() not in ALLOWED_EXTENSIONS:
        raise ValueError(f"Unsupported file type: {p.suffix}")
    if not p.is_file():
        raise FileNotFoundError(str(p))
    return p


def discover_files() -> list[FileInfo]:
    """List importable files in the historical data directory (recursive)."""
    root = settings.historical_data_dir
    out: list[FileInfo] = []
    if root.is_dir():
        for p in sorted(root.rglob("*")):
            if p.is_file() and p.suffix.lower() in ALLOWED_EXTENSIONS:
                role, desc = detect_role(p)
                out.append(FileInfo(p, str(p.relative_to(root)).replace("\\", "/"), p.stat().st_size,
                                    file_format(p), role, desc))
    legacy = legacy_db_path()
    if legacy.is_file():
        role, desc = detect_role(legacy)
        out.append(FileInfo(legacy, "backend/roaddb.db (legacy v0 database)", legacy.stat().st_size,
                            "sqlite", role, desc))
    return out


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def count_rows(path: Path) -> int | None:
    fmt = file_format(path)
    try:
        if fmt == "jsonl":
            with open(path, "rb") as fh:
                return sum(1 for line in fh if line.strip())
        if fmt == "csv":
            with open(path, "r", encoding="utf-8-sig", newline="") as fh:
                return max(0, sum(1 for _ in csv.reader(fh)) - 1)
        if fmt == "sqlite":
            con = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
            try:
                return con.execute("SELECT COUNT(*) FROM articles").fetchone()[0]
            finally:
                con.close()
    except Exception:
        return None
    return None


# --------------------------------------------------------------------------- readers
def _iter_jsonl(path: Path) -> Iterator[tuple[int, dict | None, str | None, str]]:
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        for i, line in enumerate(fh, start=1):
            if not line.strip():
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as e:
                yield i, None, f"malformed JSON: {e.msg}", line[:300]
                continue
            if not isinstance(obj, dict):
                yield i, None, "row is not a JSON object", line[:300]
                continue
            yield i, obj, None, ""


def _iter_json(path: Path) -> Iterator[tuple[int, dict | None, str | None, str]]:
    if path.stat().st_size > MAX_JSON_ARRAY_BYTES:
        raise ValueError("JSON array file is too large; convert it to JSONL")
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        data = json.load(fh)
    if isinstance(data, dict):
        for key in ("articles", "records", "items", "data"):
            if isinstance(data.get(key), list):
                data = data[key]
                break
    if not isinstance(data, list):
        raise ValueError("JSON file must contain an array of records")
    for i, obj in enumerate(data, start=1):
        if isinstance(obj, dict):
            yield i, obj, None, ""
        else:
            yield i, None, "row is not a JSON object", str(obj)[:300]


def _iter_csv(path: Path) -> Iterator[tuple[int, dict | None, str | None, str]]:
    with open(path, "r", encoding="utf-8-sig", errors="replace", newline="") as fh:
        reader = csv.DictReader(fh)
        for i, row in enumerate(reader, start=2):
            if None in row:  # more values than headers
                yield i, None, "row has more columns than the header", str(row.get(None))[:300]
                continue
            yield i, row, None, ""


def _iter_legacy_sqlite(path: Path) -> Iterator[tuple[int, dict | None, str | None, str]]:
    con = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        cols = {r[1] for r in con.execute("PRAGMA table_info(articles)")}
        if not {"title", "source_url"} <= cols:
            raise ValueError("SQLite file does not contain a compatible 'articles' table")
        for i, row in enumerate(con.execute("SELECT * FROM articles ORDER BY rowid"), start=1):
            d = dict(row)
            yield i, {
                "article_id": f"LEGACY_{d.get('id')}", "title": d.get("title"), "source_url": d.get("source_url"),
                "description": d.get("description"), "article_text": d.get("content"),
                "source": d.get("source_name"), "publication_time": d.get("published_at"),
                "retrieval_time": d.get("collected_at"), "language": d.get("language"), "city": d.get("city"),
                "source_type": "LEGACY",
                "_legacy": {"legacy_status": d.get("status"), "legacy_relevance_score": d.get("relevance_score")},
            }, None, ""
    finally:
        con.close()


def _pick(row: dict, key: str):
    for alias in FIELD_ALIASES[key]:
        if alias in row and row[alias] not in (None, ""):
            return row[alias]
    return None


def row_to_article(row: dict, role: str, file_label: str) -> ArticleIn:
    title = _pick(row, "title")
    summary_raw = _pick(row, "summary")
    body_raw = _pick(row, "text")
    title_s = str(title) if title is not None else ""
    summary_s = str(summary_raw) if summary_raw is not None else None
    body_s = str(body_raw) if body_raw is not None else None
    # In the historical files ``article_text`` repeats the RSS snippet – keep one copy.
    if body_s is not None and summary_s is not None and body_s.strip() == summary_s.strip():
        body_s = None
    source_type = str(_pick(row, "source_type") or ("LEGACY" if role == "LEGACY_DB" else "IMPORT")).upper()[:20]
    flags: dict = {}
    if role == "RAW_ARTICLES":
        flags["in_raw_file"] = True
    elif role == "DEDUPLICATED":
        flags["prior_dedup_is_duplicate"] = _as_bool(row.get("is_duplicate"))
        if row.get("deduplication_method"):
            flags["prior_dedup_method"] = row.get("deduplication_method")
    elif role == "PRIOR_RELEVANT":
        flags["prior_lexical_relevant"] = _as_bool(row.get("is_relevant"), default=True)
        if row.get("relevance_score") is not None:
            flags["prior_lexical_score"] = row.get("relevance_score")
    elif role == "WEAK_LABEL_FILE":
        flags["in_weak_label_file"] = True
    elif role == "EVAL_SPLIT":
        m = re.search(r"(dev|val|test)_split", file_label.lower())
        flags["prior_eval_split"] = m.group(1) if m else "unknown"
    elif role == "LEGACY_DB":
        flags["legacy_v0_db"] = True
        flags.update({k: v for k, v in (row.get("_legacy") or {}).items() if v is not None})
    flags = {k: v for k, v in flags.items() if v is not None}
    ext = _pick(row, "external_id")
    return ArticleIn(
        title=title_s, url=_str(_pick(row, "url")), original_url=_str(_pick(row, "original_url")),
        raw_snippet=summary_s, summary_text=summary_s, body_text=text.strip_html(body_s) if body_s else None,
        source_name=_str(_pick(row, "source")), source_type=source_type,
        connector="historical_import" if role != "LEGACY_DB" else "legacy_v0_db",
        language=_str(_pick(row, "language")), published_at=text.parse_timestamp(_pick(row, "published")),
        retrieved_at=text.parse_timestamp(_pick(row, "retrieved")), query_used=_str(_pick(row, "query")),
        query_city=_str(_pick(row, "city")), external_id=_str(ext), dataset_flags=flags)


def _str(v) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    return s or None


def _as_bool(v, default=None):
    if isinstance(v, bool):
        return v
    if v is None:
        return default
    return str(v).strip().lower() in ("true", "1", "yes")


# --------------------------------------------------------------------------- batch execution
def create_batch(db: Session, path: Path) -> ImportBatch:
    role, _ = detect_role(path)
    batch = ImportBatch(id=text.new_id("IMP_"), file_name=path.name, file_path=str(path),
                        file_size=path.stat().st_size, file_format=file_format(path), file_role=role,
                        status="QUEUED")
    db.add(batch)
    db.commit()
    return batch


def run_import(db: Session, batch_id: str, progress: Callable[[int, int, str], bool] | None = None) -> ImportBatch:
    """Execute an import batch. ``progress(done, total, msg)`` may return False to cancel."""
    batch = db.get(ImportBatch, batch_id)
    if batch is None:
        raise ValueError(f"Unknown import batch {batch_id}")
    path = Path(batch.file_path)
    batch.status, batch.started_at = "RUNNING", utcnow()
    db.commit()
    try:
        batch.file_sha256 = file_sha256(path)
        total = count_rows(path) or 0
        fmt = batch.file_format
        reader = {"jsonl": _iter_jsonl, "json": _iter_json, "csv": _iter_csv, "sqlite": _iter_legacy_sqlite}.get(fmt)
        if reader is None:
            raise ValueError(f"Unsupported format {fmt}")
        origin_label = _origin_label(path)
        ing = Ingestor(db, "LEGACY_DB" if batch.file_role == "LEGACY_DB" else "FILE", origin_label, batch.id)
        errors = 0
        n = 0
        cancelled = False
        for line_no, row, err, excerpt in reader(path):
            n += 1
            batch.discovered += 1
            if err:
                batch.invalid += 1
                errors += _record_error(db, batch, line_no, "INVALID", err, excerpt, errors)
            else:
                try:
                    with db.begin_nested():
                        rec = row_to_article(row, batch.file_role or "GENERIC", path.name)
                        outcome = ing.ingest(rec)
                        db.flush()
                except Exception as e:  # one bad row must not abort the batch
                    log.exception("Import row %s failed", line_no)
                    outcome = None
                    batch.failed += 1
                    errors += _record_error(db, batch, line_no, "FAILED", f"{type(e).__name__}: {e}",
                                            json.dumps(row, default=str)[:300], errors)
                if outcome is not None:
                    if outcome.status == "NEW":
                        batch.imported += 1
                    elif outcome.status == "DUPLICATE":
                        batch.duplicate += 1
                    else:
                        batch.invalid += 1
                        errors += _record_error(db, batch, line_no, "INVALID", outcome.reason or "invalid",
                                                text.truncate(str(row.get("title") or row)[:300], 300), errors)
            if n % COMMIT_EVERY == 0:
                db.commit()
                if progress and progress(n, total, f"{n:,} of {total:,} rows") is False:
                    cancelled = True
                    break
        db.commit()
        batch.finished_at = utcnow()
        if cancelled:
            batch.status = "CANCELLED"
            batch.skipped = max(0, total - n)
        elif batch.failed or batch.invalid:
            batch.status = "COMPLETED_WITH_ERRORS"
        else:
            batch.status = "COMPLETED"
        batch.message = (f"discovered={batch.discovered} imported={batch.imported} duplicate={batch.duplicate} "
                         f"invalid={batch.invalid} failed={batch.failed} skipped={batch.skipped}")
        db.commit()
        if progress:
            progress(n, total, batch.message)
        log.info("Import %s (%s): %s", batch.id, path.name, batch.message)
    except Exception as e:
        db.rollback()
        batch = db.get(ImportBatch, batch_id)
        batch.status, batch.finished_at = "FAILED", utcnow()
        batch.message = f"{type(e).__name__}: {e}"
        db.commit()
        log.exception("Import %s failed", batch_id)
    return batch


def _origin_label(path: Path) -> str:
    try:
        return "data/" + str(path.relative_to(settings.historical_data_dir)).replace("\\", "/")
    except ValueError:
        return path.name


def _record_error(db: Session, batch: ImportBatch, line_no: int, cat: str, reason: str, excerpt: str,
                  current: int) -> int:
    if current >= MAX_ROW_ERRORS:
        return 0
    db.add(ImportRowError(batch_id=batch.id, line_no=line_no, category=cat, reason=reason[:500],
                          excerpt=(excerpt or "")[:300]))
    return 1


def error_report_csv(db: Session, batch_id: str) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["batch_id", "line_no", "category", "reason", "excerpt"])
    for e in db.scalars(select(ImportRowError).where(ImportRowError.batch_id == batch_id)
                        .order_by(ImportRowError.line_no)):
        w.writerow([e.batch_id, e.line_no, e.category, e.reason, e.excerpt])
    return buf.getvalue()


def import_history(db: Session) -> dict:
    """Latest completed batch per file path/sha – used to show 'already imported'."""
    rows = db.execute(select(ImportBatch.file_path, ImportBatch.file_sha256, func.max(ImportBatch.finished_at))
                      .where(ImportBatch.status.in_(["COMPLETED", "COMPLETED_WITH_ERRORS"]))
                      .group_by(ImportBatch.file_path, ImportBatch.file_sha256)).all()
    return {r[0]: {"sha256": r[1], "finished_at": r[2]} for r in rows}


def sanitize_upload_name(name: str) -> str:
    base = Path(name or "upload").name
    stem = re.sub(r"[^A-Za-z0-9._-]", "_", Path(base).stem)[:80] or "upload"
    ext = Path(base).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS - {".db", ".sqlite"}:
        raise ValueError("Only .jsonl, .ndjson, .json and .csv uploads are accepted")
    return f"{stem}{ext}"
