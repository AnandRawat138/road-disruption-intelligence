"""Text, URL, hashing and timestamp normalisation helpers."""
from __future__ import annotations

import hashlib
import html
import re
import uuid
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")
_NON_WORD_RE = re.compile(r"[^\w\s]", re.UNICODE)

# Query parameters that never change the identity of an article.
TRACKING_PARAMS = {
    "oc", "ocid", "ref", "ref_src", "ref_url", "fbclid", "gclid", "dclid", "msclkid", "cmpid",
    "from", "source", "src", "share", "amp", "output", "ito", "s_cid", "mc_cid", "mc_eid", "igshid",
}


def new_id(prefix: str = "") -> str:
    return f"{prefix}{uuid.uuid4().hex[:20]}"


def strip_html(value: str | None) -> str:
    if not value:
        return ""
    text = _TAG_RE.sub(" ", value)
    text = html.unescape(text).replace("\xa0", " ")
    return _WS_RE.sub(" ", text).strip()


def canonicalize_url(url: str | None) -> str | None:
    """Stable canonical form used for exact deduplication.

    Lower-cases scheme/host, drops ``www.``, fragments, tracking parameters and
    trailing slashes, sorts remaining query parameters and unifies Google News
    ``/rss/articles/<id>`` and ``/articles/<id>`` links.
    """
    if not url or not isinstance(url, str):
        return None
    url = url.strip()
    if not re.match(r"^https?://", url, re.I):
        return None
    try:
        parts = urlsplit(url)
    except ValueError:
        return None
    host = (parts.hostname or "").lower()
    if not host:
        return None
    if host.startswith("www."):
        host = host[4:]
    if parts.port and parts.port not in (80, 443):
        host = f"{host}:{parts.port}"
    path = parts.path or "/"
    if host == "news.google.com":
        path = re.sub(r"^/rss/articles/", "/articles/", path)
    if len(path) > 1 and path.endswith("/"):
        path = path.rstrip("/")
    query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=False)
             if not k.lower().startswith("utm_") and k.lower() not in TRACKING_PARAMS]
    query.sort()
    return urlunsplit(("https", host, path, urlencode(query), ""))


def article_id_for(canonical_url: str | None, fallback_key: str) -> str:
    key = canonical_url or f"nourl:{fallback_key}"
    return "A" + hashlib.sha256(key.encode("utf-8")).hexdigest()[:23]


def strip_publisher_suffix(title: str, source_name: str | None = None) -> str:
    """Google News titles end with `` - Publisher``; remove it for comparison."""
    t = (title or "").strip()
    if source_name and t.lower().endswith(f" - {source_name.lower()}"):
        return t[: -(len(source_name) + 3)].strip()
    m = re.match(r"^(.*\S)\s+[-|–]\s+[^-|–]{2,60}$", t)
    if m and len(m.group(1)) >= 20:
        return m.group(1).strip()
    return t


def normalize_title(title: str, source_name: str | None = None) -> str:
    t = strip_publisher_suffix(strip_html(title), source_name).lower()
    t = _NON_WORD_RE.sub(" ", t)
    return _WS_RE.sub(" ", t).strip()


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def content_hash(title_norm: str, summary: str) -> str:
    return sha256(f"{title_norm}|{_WS_RE.sub(' ', (summary or '').lower()).strip()}")


def title_fingerprint(title_norm: str, source_name: str | None) -> str | None:
    """Fingerprint of (normalised title, source) for near-duplicate detection.

    Very short titles are too generic to fingerprint safely.
    """
    if len(title_norm.split()) < 6:
        return None
    return sha256(f"{(source_name or '').strip().lower()}|{title_norm}")


def to_naive_utc(dt: datetime) -> datetime:
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def parse_timestamp(value) -> datetime | None:
    """Parse RFC 822, ISO 8601 and GDELT ``YYYYMMDDTHHMMSSZ`` timestamps to naive UTC."""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return to_naive_utc(value)
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(float(value), tz=timezone.utc).replace(tzinfo=None)
        except (OverflowError, OSError, ValueError):
            return None
    s = str(value).strip()
    m = re.fullmatch(r"(\d{8})T(\d{6})Z?", s)
    if m:
        try:
            return datetime.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M%S")
        except ValueError:
            return None
    try:
        return to_naive_utc(datetime.fromisoformat(s.replace("Z", "+00:00")))
    except ValueError:
        pass
    try:
        return to_naive_utc(parsedate_to_datetime(s))
    except (TypeError, ValueError, IndexError):
        pass
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def plausible_timestamp(dt: datetime | None, now: datetime | None = None) -> bool:
    if dt is None:
        return False
    now = now or datetime.now(timezone.utc).replace(tzinfo=None)
    return datetime(1995, 1, 1) <= dt <= now.replace(year=now.year + 1)


def truncate(text: str | None, n: int) -> str:
    if not text:
        return ""
    return text if len(text) <= n else text[: n - 1] + "…"
