"""RSS-based connectors: Google News search RSS and operator-supplied RSS/Atom feeds."""
from __future__ import annotations

import itertools
import urllib.parse
from datetime import datetime, timedelta, timezone

import feedparser

from ..ingest import ArticleIn
from ..text import parse_timestamp, strip_html
from .base import Connector, ConnectorError, FetchResult

DEFAULT_TERMS = [
    "road closed", "traffic diversion", "traffic advisory", "traffic jam", "highway blocked", "waterlogging traffic",
    "landslide highway", "road accident highway", "protest road blockade", "VIP movement traffic restrictions",
    "road construction diversion", "bridge collapse road",
]
DEFAULT_PLACES = ["Mumbai", "Thane", "Navi Mumbai", "Pune", "Delhi", "Gurugram", "Noida", "Bengaluru", "Chennai",
                  "Hyderabad", "Kolkata", "Ahmedabad", "Mumbai-Pune Expressway", "Mumbai-Goa highway", "India"]


def _parse_feed(content: bytes, label: str):
    feed = feedparser.parse(content)
    if feed.bozo and not feed.entries:
        raise ConnectorError("PARSE", f"{label}: response is not a valid RSS/Atom feed "
                                      f"({type(feed.bozo_exception).__name__})")
    return feed


def _entry_time(entry) -> datetime | None:
    for key in ("published", "updated", "pubDate"):
        if entry.get(key):
            ts = parse_timestamp(entry.get(key))
            if ts:
                return ts
    return None


class GoogleNewsRSSConnector(Connector):
    type_id = "google_news_rss"
    display_name = "Google News RSS"
    description = "Google News search results as RSS (headline + publisher only, no article body)."
    access_notes = ("Public RSS endpoint; no key required. Unofficial for programmatic use – keep polling gentle. "
                    "Provides headlines and links only; results are a sample, not complete coverage.")
    default_config = {"terms": DEFAULT_TERMS, "places": DEFAULT_PLACES, "when": "3d", "language": "en-IN",
                      "country": "IN", "queries_per_run": 12, "request_spacing_seconds": 3}

    def _combos(self) -> list[str]:
        terms = [t for t in self.cfg.get("terms") or [] if t.strip()]
        places = [p for p in self.cfg.get("places") or [] if p.strip()] or [""]
        return [f"{t} {p}".strip() for t, p in itertools.product(terms, places)]

    def fetch(self, limit: int) -> FetchResult:
        res = FetchResult()
        combos = self._combos()
        if not combos:
            raise ConnectorError("NOT_CONFIGURED", "No search terms configured")
        per_run = max(1, min(int(self.cfg.get("queries_per_run", 12)), 50))
        cursor = int(self.cfg.get("_cursor", 0)) % len(combos)
        batch = [combos[(cursor + i) % len(combos)] for i in range(min(per_run, len(combos)))]
        res.state_updates["_cursor"] = (cursor + len(batch)) % len(combos)
        when = self.cfg.get("when") or "3d"
        hl, gl = self.cfg.get("language", "en-IN"), self.cfg.get("country", "IN")
        ceid = f"{gl}:{hl.split('-')[0]}"
        client = self._client()
        seen: set[str] = set()
        try:
            for i, q in enumerate(batch):
                if len(res.items) >= limit:
                    break
                if i:
                    self.sleep(float(self.cfg.get("request_spacing_seconds", 3)))
                url = "https://news.google.com/rss/search"
                params = {"q": f"{q} when:{when}", "hl": hl, "gl": gl, "ceid": ceid}
                try:
                    resp = self._get(client, url, params=params)
                    res.requests += 1
                    feed = _parse_feed(resp.content, self.display_name)
                except ConnectorError as e:
                    res.requests += 1
                    res.errors.append(f"query '{q}': {e}")
                    if e.kind in ("AUTH", "RATE_LIMITED"):
                        res.partial = True
                        break
                    continue
                for entry in feed.entries:
                    link = entry.get("link")
                    if not link or link in seen:
                        continue
                    seen.add(link)
                    src = entry.get("source") or {}
                    res.items.append(ArticleIn(
                        title=entry.get("title", ""), url=link, raw_snippet=entry.get("summary"),
                        summary_text=entry.get("summary"), source_name=src.get("title") if isinstance(src, dict) else None,
                        source_type="RSS", connector=self.type_id, language="en", published_at=_entry_time(entry),
                        retrieved_at=datetime.now(timezone.utc).replace(tzinfo=None), query_used=q,
                        query_city=None, external_id=None))
                    if len(res.items) >= limit:
                        break
        finally:
            if self.client is None:
                client.close()
        res.notes.append(f"Queried {len(batch)} of {len(combos)} search combinations this run (rotating).")
        return res


class CustomRSSConnector(Connector):
    type_id = "custom_rss"
    display_name = "Custom RSS/Atom feeds"
    description = "Operator-supplied RSS/Atom feeds, e.g. official traffic police, highway authority or disaster feeds."
    access_notes = "Add only feeds you are permitted to poll. Items are filtered by the keyword pre-filter if enabled."
    default_config = {"feeds": [], "only_matching_keywords": True, "request_spacing_seconds": 2}

    def configuration_status(self) -> tuple[str, str]:
        feeds = [f for f in self.cfg.get("feeds") or [] if str(f).startswith(("http://", "https://"))]
        if not feeds:
            return "NOT_CONFIGURED", "No feed URLs configured"
        return "CONFIGURED", f"{len(feeds)} feed(s) configured"

    def fetch(self, limit: int) -> FetchResult:
        from .. import prefilter
        res = FetchResult()
        feeds = [f for f in self.cfg.get("feeds") or [] if str(f).startswith(("http://", "https://"))]
        if not feeds:
            raise ConnectorError("NOT_CONFIGURED", "No feed URLs configured")
        client = self._client()
        try:
            for i, feed_url in enumerate(feeds):
                if i:
                    self.sleep(float(self.cfg.get("request_spacing_seconds", 2)))
                try:
                    resp = self._get(client, feed_url)
                    res.requests += 1
                    feed = _parse_feed(resp.content, feed_url)
                except ConnectorError as e:
                    res.requests += 1
                    res.errors.append(f"{feed_url}: {e}")
                    continue
                host = urllib.parse.urlsplit(feed_url).hostname or feed_url
                feed_title = (feed.feed.get("title") if hasattr(feed, "feed") else None) or host
                for entry in feed.entries:
                    title = entry.get("title", "")
                    summary = entry.get("summary") or entry.get("description")
                    if self.cfg.get("only_matching_keywords", True):
                        if prefilter.assess(title, strip_html(summary)).label == "UNLIKELY":
                            continue
                    res.items.append(ArticleIn(
                        title=title, url=entry.get("link"), raw_snippet=summary, summary_text=summary,
                        source_name=feed_title[:200], source_type="RSS", connector=self.type_id,
                        published_at=_entry_time(entry), retrieved_at=datetime.now(timezone.utc).replace(tzinfo=None),
                        query_used=f"feed:{host}"))
                    if len(res.items) >= limit:
                        return res
        finally:
            if self.client is None:
                client.close()
        return res


def recent_enough(dt: datetime | None, days: int) -> bool:
    if dt is None:
        return True
    return dt >= datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=days)
