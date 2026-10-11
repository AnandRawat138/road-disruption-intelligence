"""Idempotent article ingestion shared by file imports and live connectors.

Deduplication order (first match wins):
  1. Exact canonical URL.
  2. Same external id seen before (e.g. the dataset's ``article_id``).
  3. Same content hash (normalised title + summary) from the same source.
  4. Same normalised title from the same source published within 3 days
     (syndicated re-posts / URL variants).

Reports from *different* sources are never merged here – they remain
separate articles and are linked later as evidence of the same incident.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db.models import Article, ArticleSighting, utcnow
from . import prefilter, text

log = logging.getLogger(__name__)

NEAR_DUP_WINDOW = timedelta(days=3)
MAX_TITLE = 1000
MAX_TEXT = 200_000


@dataclass
class ArticleIn:
    title: str
    url: str | None = None
    original_url: str | None = None
    raw_snippet: str | None = None
    summary_text: str | None = None
    body_text: str | None = None
    source_name: str | None = None
    source_type: str = "RSS"
    connector: str | None = None
    language: str | None = None
    published_at: datetime | None = None
    retrieved_at: datetime | None = None
    query_used: str | None = None
    query_city: str | None = None
    external_id: str | None = None
    dataset_flags: dict = field(default_factory=dict)


@dataclass
class IngestOutcome:
    status: str  # NEW / DUPLICATE / INVALID
    article_id: str | None = None
    method: str | None = None
    reason: str | None = None
    prefilter_label: str | None = None


class Ingestor:
    """Stateful helper that caches dedup keys for the lifetime of one batch."""

    def __init__(self, db: Session, origin_type: str, origin: str, batch_id: str | None = None):
        self.db = db
        self.origin_type = origin_type
        self.origin = origin[:200]
        self.batch_id = batch_id
        self._url: dict[str, str] = {}
        self._ext: dict[str, str] = {}
        self._hash: dict[tuple[str, str], str] = {}
        self._fp: dict[str, tuple[str, datetime | None]] = {}
        self._sightings: set[tuple] = set()
        self._load()

    def _load(self) -> None:
        rows = self.db.execute(select(Article.id, Article.canonical_url, Article.content_hash, Article.source_name,
                                      Article.title_fingerprint, Article.published_at)).all()
        for aid, url, ch, src, fp, pub in rows:
            if url:
                self._url[url] = aid
            if ch:
                self._hash[(ch, (src or "").lower())] = aid
            if fp:
                self._fp[fp] = (aid, pub)
        for aid, ext in self.db.execute(select(ArticleSighting.article_id, ArticleSighting.external_id)
                                        .where(ArticleSighting.external_id != "")).all():
            self._ext[ext] = aid

    # ------------------------------------------------------------------
    def validate(self, rec: ArticleIn) -> str | None:
        if not rec.title or not text.strip_html(rec.title):
            return "missing title"
        if len(rec.title) > MAX_TITLE:
            return "title too long"
        canon = text.canonicalize_url(rec.url) if rec.url else None
        if rec.url and not canon:
            return f"invalid URL: {text.truncate(rec.url, 80)}"
        if not canon and not rec.external_id and not rec.published_at:
            return "no URL, external id or publication time to identify the record"
        if rec.published_at and not text.plausible_timestamp(rec.published_at):
            return f"implausible publication time {rec.published_at.isoformat()}"
        return None

    def ingest(self, rec: ArticleIn) -> IngestOutcome:
        problem = self.validate(rec)
        if problem:
            return IngestOutcome("INVALID", reason=problem)

        title = text.strip_html(rec.title)
        source = (rec.source_name or "").strip()[:200] or None
        summary = text.strip_html(rec.summary_text if rec.summary_text is not None else rec.raw_snippet)
        canon = text.canonicalize_url(rec.url)
        title_norm = text.normalize_title(title, source)
        chash = text.content_hash(title_norm, summary)
        fp = text.title_fingerprint(title_norm, source)

        existing, method = None, None
        if canon and canon in self._url:
            existing, method = self._url[canon], "canonical_url"
        elif rec.external_id and rec.external_id in self._ext:
            existing, method = self._ext[rec.external_id], "external_id"
        elif (chash, (source or "").lower()) in self._hash:
            existing, method = self._hash[(chash, (source or "").lower())], "content_hash"
        elif fp and fp in self._fp:
            cand_id, cand_pub = self._fp[fp]
            if rec.published_at is None or cand_pub is None or abs(rec.published_at - cand_pub) <= NEAR_DUP_WINDOW:
                existing, method = cand_id, "title_fingerprint"

        if existing:
            self._add_sighting(existing, rec, method)
            if rec.dataset_flags:
                art = self.db.get(Article, existing)
                if art is not None:
                    merged = dict(art.dataset_flags or {})
                    merged.update(rec.dataset_flags)
                    if merged != art.dataset_flags:
                        art.dataset_flags = merged
            return IngestOutcome("DUPLICATE", article_id=existing, method=method)

        aid = text.article_id_for(canon, f"{rec.external_id}|{chash}")
        if self.db.get(Article, aid) is not None:  # extremely unlikely hash collision / race
            self._add_sighting(aid, rec, "article_id")
            return IngestOutcome("DUPLICATE", article_id=aid, method="article_id")

        pf = prefilter.assess(title, summary if summary != title else "")
        art = Article(
            id=aid, canonical_url=canon, source_url=rec.url, original_url=rec.original_url or rec.url,
            title=title, title_norm=title_norm, title_fingerprint=fp, content_hash=chash,
            summary_text=summary[:MAX_TEXT] or None,
            body_text=(rec.body_text or "")[:MAX_TEXT] or None,
            raw_snippet=(rec.raw_snippet or "")[:MAX_TEXT] or None,
            source_name=source, source_type=rec.source_type, connector=rec.connector,
            language=_norm_lang(rec.language), published_at=rec.published_at, retrieved_at=rec.retrieved_at,
            ingested_at=utcnow(), query_used=rec.query_used, query_city=rec.query_city,
            external_ids=[rec.external_id] if rec.external_id else [],
            dataset_flags=dict(rec.dataset_flags or {}),
            prefilter_label=pf.label, prefilter_score=pf.score, prefilter_reason=pf.reason,
        )
        self.db.add(art)
        if canon:
            self._url[canon] = aid
        self._hash[(chash, (source or "").lower())] = aid
        if fp:
            self._fp[fp] = (aid, rec.published_at)
        self._add_sighting(aid, rec, "new")
        return IngestOutcome("NEW", article_id=aid, method="new", prefilter_label=pf.label)

    def _add_sighting(self, aid: str, rec: ArticleIn, method: str | None) -> None:
        ext = (rec.external_id or "")[:200]
        q = (rec.query_used or "")[:500]
        key = (aid, self.origin, ext, q)
        if key in self._sightings:
            return
        self._sightings.add(key)
        exists = self.db.scalar(select(ArticleSighting.id).where(
            ArticleSighting.article_id == aid, ArticleSighting.origin == self.origin,
            ArticleSighting.external_id == ext, ArticleSighting.query_used == q))
        if exists:
            return
        self.db.add(ArticleSighting(article_id=aid, origin_type=self.origin_type, origin=self.origin,
                                    external_id=ext, query_used=q, url=rec.url, match_method=method,
                                    batch_id=self.batch_id, seen_at=utcnow()))
        if ext:
            self._ext.setdefault(ext, aid)


def _norm_lang(lang: str | None) -> str | None:
    if not lang:
        return None
    m = {"english": "en", "hindi": "hi", "marathi": "mr", "tamil": "ta", "telugu": "te", "bengali": "bn",
         "kannada": "kn", "malayalam": "ml", "gujarati": "gu", "punjabi": "pa", "urdu": "ur"}
    low = lang.strip().lower()
    return m.get(low, low[:10])
