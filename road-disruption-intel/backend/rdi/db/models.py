"""SQLAlchemy ORM models.

Design notes
------------
* ``Article`` is one unique source document (deduplicated by canonical URL).
  Every time the same article is seen again (in another file, query or fetch
  run) an ``ArticleSighting`` row records that provenance.
* ``Classification`` rows are append-only versions. Exactly one row per
  article has ``is_current = True``. Human corrections are stored as new
  versions with ``origin = 'HUMAN'`` so the model output is never overwritten.
* ``Incident`` groups related articles that describe the same real-world
  event. Source articles are never deleted when incidents change.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (JSON, Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text,
                        UniqueConstraint)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow() -> datetime:
    """Naive UTC timestamp (SQLite stores naive datetimes)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Base(DeclarativeBase):
    pass


class SchemaVersion(Base):
    __tablename__ = "schema_version"
    version: Mapped[int] = mapped_column(Integer, primary_key=True)
    applied_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    note: Mapped[str | None] = mapped_column(String(200))


class Article(Base):
    __tablename__ = "articles"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    canonical_url: Mapped[str | None] = mapped_column(Text, unique=True)
    source_url: Mapped[str | None] = mapped_column(Text)
    original_url: Mapped[str | None] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text, default="")
    title_norm: Mapped[str] = mapped_column(Text, default="")
    title_fingerprint: Mapped[str | None] = mapped_column(String(64), index=True)
    content_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    summary_text: Mapped[str | None] = mapped_column(Text)
    body_text: Mapped[str | None] = mapped_column(Text)
    raw_snippet: Mapped[str | None] = mapped_column(Text)
    source_name: Mapped[str | None] = mapped_column(String(200), index=True)
    source_type: Mapped[str] = mapped_column(String(20), default="RSS")
    connector: Mapped[str | None] = mapped_column(String(60), index=True)
    language: Mapped[str | None] = mapped_column(String(20))
    published_at: Mapped[datetime | None] = mapped_column(DateTime, index=True)
    retrieved_at: Mapped[datetime | None] = mapped_column(DateTime)
    ingested_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)
    query_used: Mapped[str | None] = mapped_column(Text)
    query_city: Mapped[str | None] = mapped_column(String(100))
    external_ids: Mapped[list] = mapped_column(JSON, default=list)
    dataset_flags: Mapped[dict] = mapped_column(JSON, default=dict)

    prefilter_label: Mapped[str | None] = mapped_column(String(30), index=True)
    prefilter_score: Mapped[float | None] = mapped_column(Float)
    prefilter_reason: Mapped[str | None] = mapped_column(Text)

    near_duplicate_of: Mapped[str | None] = mapped_column(String(32), index=True)
    dedup_note: Mapped[str | None] = mapped_column(Text)

    classification_status: Mapped[str] = mapped_column(String(20), default="UNCLASSIFIED", index=True)
    review_status: Mapped[str] = mapped_column(String(20), default="UNREVIEWED", index=True)
    current_classification_id: Mapped[str | None] = mapped_column(String(32), index=True)
    incident_id: Mapped[str | None] = mapped_column(String(32), index=True)
    classification_attempts: Mapped[int] = mapped_column(Integer, default=0)


class ArticleSighting(Base):
    __tablename__ = "article_sightings"
    __table_args__ = (UniqueConstraint("article_id", "origin", "external_id", "query_used", name="uq_sighting"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    article_id: Mapped[str] = mapped_column(String(32), ForeignKey("articles.id", ondelete="CASCADE"), index=True)
    origin_type: Mapped[str] = mapped_column(String(20))  # FILE / CONNECTOR / LEGACY_DB / UPLOAD
    origin: Mapped[str] = mapped_column(String(200))
    external_id: Mapped[str] = mapped_column(String(200), default="", index=True)
    query_used: Mapped[str] = mapped_column(Text, default="")
    url: Mapped[str | None] = mapped_column(Text)
    match_method: Mapped[str | None] = mapped_column(String(30))  # how it was matched to the article
    batch_id: Mapped[str | None] = mapped_column(String(40))
    seen_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Classification(Base):
    __tablename__ = "classifications"
    __table_args__ = (Index("ix_class_article_current", "article_id", "is_current"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    article_id: Mapped[str] = mapped_column(String(32), ForeignKey("articles.id", ondelete="CASCADE"), index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    is_current: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    origin: Mapped[str] = mapped_column(String(10), default="MODEL")  # MODEL / HUMAN
    provider: Mapped[str | None] = mapped_column(String(40))
    model: Mapped[str | None] = mapped_column(String(120))
    prompt_version: Mapped[str | None] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    created_by: Mapped[str | None] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(10), default="VALID", index=True)  # VALID / INVALID / FAILED
    error: Mapped[str | None] = mapped_column(Text)
    raw_output: Mapped[str | None] = mapped_column(Text)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    input_chars: Mapped[int | None] = mapped_column(Integer)

    relevance: Mapped[str | None] = mapped_column(String(20), index=True)
    category: Mapped[str | None] = mapped_column(String(30), index=True)
    country: Mapped[str | None] = mapped_column(String(60))
    state: Mapped[str | None] = mapped_column(String(80), index=True)
    city: Mapped[str | None] = mapped_column(String(100), index=True)
    locality: Mapped[str | None] = mapped_column(String(200))
    road_name: Mapped[str | None] = mapped_column(String(200))
    highway_number: Mapped[str | None] = mapped_column(String(40), index=True)
    direction: Mapped[str | None] = mapped_column(String(100))
    affected_segment: Mapped[str | None] = mapped_column(Text)
    event_start: Mapped[datetime | None] = mapped_column(DateTime)
    event_end: Mapped[datetime | None] = mapped_column(DateTime)
    time_status: Mapped[str | None] = mapped_column(String(12))  # ONGOING / UPCOMING / RESOLVED / UNKNOWN
    severity: Mapped[str | None] = mapped_column(String(10), index=True)
    reported_delay: Mapped[str | None] = mapped_column(Text)
    advisory_action: Mapped[str | None] = mapped_column(Text)
    summary: Mapped[str | None] = mapped_column(Text)
    evidence_excerpt: Mapped[str | None] = mapped_column(Text)
    evidence_verified: Mapped[bool | None] = mapped_column(Boolean)
    model_confidence: Mapped[str | None] = mapped_column(String(10))
    validation_status: Mapped[str | None] = mapped_column(String(10))  # PASSED / WARNINGS / FAILED
    validation_issues: Mapped[list] = mapped_column(JSON, default=list)
    missing_fields: Mapped[list] = mapped_column(JSON, default=list)
    needs_review: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    review_reasons: Mapped[list] = mapped_column(JSON, default=list)

    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    geo_status: Mapped[str | None] = mapped_column(String(12), index=True)  # RESOLVED / APPROXIMATE / UNRESOLVED
    geo_precision: Mapped[str | None] = mapped_column(String(12))  # LOCALITY / CITY / STATE / MANUAL
    geo_method: Mapped[str | None] = mapped_column(String(20))  # GAZETTEER / NOMINATIM / MANUAL
    geo_query: Mapped[str | None] = mapped_column(Text)
    geo_display_name: Mapped[str | None] = mapped_column(Text)
    geo_confidence: Mapped[str | None] = mapped_column(String(10))


class Incident(Base):
    __tablename__ = "incidents"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    title: Mapped[str] = mapped_column(Text)
    category: Mapped[str | None] = mapped_column(String(30), index=True)
    severity: Mapped[str | None] = mapped_column(String(10), index=True)
    status: Mapped[str] = mapped_column(String(12), default="NEW", index=True)
    time_status: Mapped[str | None] = mapped_column(String(12))
    state: Mapped[str | None] = mapped_column(String(80), index=True)
    city: Mapped[str | None] = mapped_column(String(100), index=True)
    locality: Mapped[str | None] = mapped_column(String(200))
    road_name: Mapped[str | None] = mapped_column(String(200))
    highway_number: Mapped[str | None] = mapped_column(String(40), index=True)
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    geo_precision: Mapped[str | None] = mapped_column(String(12))
    first_reported_at: Mapped[datetime | None] = mapped_column(DateTime, index=True)
    last_reported_at: Mapped[datetime | None] = mapped_column(DateTime, index=True)
    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime)
    event_start: Mapped[datetime | None] = mapped_column(DateTime)
    event_end: Mapped[datetime | None] = mapped_column(DateTime)
    article_count: Mapped[int] = mapped_column(Integer, default=0)
    has_conflict: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    conflict_notes: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class IncidentHistory(Base):
    __tablename__ = "incident_history"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    incident_id: Mapped[str] = mapped_column(String(32), ForeignKey("incidents.id", ondelete="CASCADE"), index=True)
    from_status: Mapped[str | None] = mapped_column(String(12))
    to_status: Mapped[str] = mapped_column(String(12))
    changed_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    actor: Mapped[str] = mapped_column(String(100), default="system")
    note: Mapped[str | None] = mapped_column(Text)


class AuditLog(Base):
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    actor: Mapped[str] = mapped_column(String(100), default="system")
    entity_type: Mapped[str] = mapped_column(String(30), index=True)
    entity_id: Mapped[str] = mapped_column(String(64), index=True)
    action: Mapped[str] = mapped_column(String(40))
    details: Mapped[dict] = mapped_column(JSON, default=dict)


class Source(Base):
    __tablename__ = "sources"
    id: Mapped[str] = mapped_column(String(60), primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    connector_type: Mapped[str] = mapped_column(String(40))
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    config: Mapped[dict] = mapped_column(JSON, default=dict)
    poll_interval_minutes: Mapped[int] = mapped_column(Integer, default=120)
    max_records: Mapped[int] = mapped_column(Integer, default=50)
    timeout_seconds: Mapped[int] = mapped_column(Integer, default=20)
    max_retries: Mapped[int] = mapped_column(Integer, default=3)
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime)
    last_status: Mapped[str | None] = mapped_column(String(20))
    last_error: Mapped[str | None] = mapped_column(Text)
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0)
    total_fetched: Mapped[int] = mapped_column(Integer, default=0)
    total_new: Mapped[int] = mapped_column(Integer, default=0)
    total_duplicates: Mapped[int] = mapped_column(Integer, default=0)
    total_relevant: Mapped[int] = mapped_column(Integer, default=0)
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class FetchRun(Base):
    __tablename__ = "fetch_runs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_id: Mapped[str] = mapped_column(String(60), index=True)
    trigger: Mapped[str] = mapped_column(String(12), default="MANUAL")
    started_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)
    status: Mapped[str] = mapped_column(String(20), default="RUNNING")
    fetched: Mapped[int] = mapped_column(Integer, default=0)
    new: Mapped[int] = mapped_column(Integer, default=0)
    duplicates: Mapped[int] = mapped_column(Integer, default=0)
    invalid: Mapped[int] = mapped_column(Integer, default=0)
    relevant: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text)
    details: Mapped[dict] = mapped_column(JSON, default=dict)


class ImportBatch(Base):
    __tablename__ = "import_batches"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    file_name: Mapped[str] = mapped_column(String(255))
    file_path: Mapped[str] = mapped_column(Text)
    file_sha256: Mapped[str | None] = mapped_column(String(64), index=True)
    file_size: Mapped[int | None] = mapped_column(Integer)
    file_format: Mapped[str | None] = mapped_column(String(10))
    file_role: Mapped[str | None] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(30), default="QUEUED", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)
    discovered: Mapped[int] = mapped_column(Integer, default=0)
    imported: Mapped[int] = mapped_column(Integer, default=0)
    duplicate: Mapped[int] = mapped_column(Integer, default=0)
    skipped: Mapped[int] = mapped_column(Integer, default=0)
    invalid: Mapped[int] = mapped_column(Integer, default=0)
    failed: Mapped[int] = mapped_column(Integer, default=0)
    message: Mapped[str | None] = mapped_column(Text)
    job_id: Mapped[str | None] = mapped_column(String(32))


class ImportRowError(Base):
    __tablename__ = "import_row_errors"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    batch_id: Mapped[str] = mapped_column(String(40), ForeignKey("import_batches.id", ondelete="CASCADE"), index=True)
    line_no: Mapped[int] = mapped_column(Integer)
    category: Mapped[str] = mapped_column(String(20))  # INVALID / FAILED / SKIPPED
    reason: Mapped[str] = mapped_column(Text)
    excerpt: Mapped[str | None] = mapped_column(Text)


class Job(Base):
    __tablename__ = "jobs"
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    job_type: Mapped[str] = mapped_column(String(40), index=True)
    status: Mapped[str] = mapped_column(String(20), default="QUEUED", index=True)
    params: Mapped[dict] = mapped_column(JSON, default=dict)
    total: Mapped[int] = mapped_column(Integer, default=0)
    processed: Mapped[int] = mapped_column(Integer, default=0)
    succeeded: Mapped[int] = mapped_column(Integer, default=0)
    failed: Mapped[int] = mapped_column(Integer, default=0)
    message: Mapped[str | None] = mapped_column(Text)
    result: Mapped[dict] = mapped_column(JSON, default=dict)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False)
    created_by: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)
    dedup_key: Mapped[str | None] = mapped_column(String(120), index=True)


class AppSetting(Base):
    __tablename__ = "app_settings"
    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value: Mapped[dict | list | str | int | float | bool | None] = mapped_column(JSON)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class GeocodeCache(Base):
    __tablename__ = "geocode_cache"
    key: Mapped[str] = mapped_column(String(300), primary_key=True)
    provider: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(12))  # OK / NOT_FOUND / ERROR
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    display_name: Mapped[str | None] = mapped_column(Text)
    precision: Mapped[str | None] = mapped_column(String(12))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Alert(Base):
    __tablename__ = "alerts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    incident_id: Mapped[str] = mapped_column(String(32), index=True)
    rule: Mapped[str] = mapped_column(String(60))
    message: Mapped[str] = mapped_column(Text)
    severity: Mapped[str | None] = mapped_column(String(10))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    read_at: Mapped[datetime | None] = mapped_column(DateTime)
    dedup_key: Mapped[str] = mapped_column(String(120), unique=True)


Index("ix_articles_status_pub", Article.classification_status, Article.published_at)
Index("ix_class_current_cat", Classification.is_current, Classification.category)
