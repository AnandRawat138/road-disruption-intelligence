"""Highway references in reports and the per-highway view of possibly running events.

Highways are recognised only where a report names them; nothing is inferred
from coordinates. Four reference types are extracted from text:

* numbered national highways   – "NH-48", "NH 44", "National Highway 66"  -> ``NH-48``
* numbered state highways      – "SH 10", "State Highway 7"               -> ``SH-10`` (+ state when known)
* named expressways            – "Mumbai-Pune Expressway", "Yamuna Expressway"
* named highways               – "Mumbai-Goa highway", "Western Express Highway"

A highway has a *possibly running* event when an active incident (NEW,
MONITORING or CONFIRMED and not reported as resolved) names it, or when a recent
unclassified report that the keyword pre-filter marks as relevant names it.
Unclassified reports are shown separately as unverified.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..db.models import Article, Classification, Incident, utcnow
from . import incidents as inc_svc, settings_store
from .geo.gazetteer_data import ALIASES, CITIES
from .geo.geocoder import normalize_city

_NUMBERED = re.compile(
    r"(?<![A-Za-z])(NH|N\.H\.|National\s+Highway|SH|S\.H\.|State\s+Highway)\s*(?:No\.?\s*)?[-–:]?\s*"
    r"(\d{1,4}[A-Ca-c]?)(?![\w-])", re.I)
# Words that are capitalised in Title-Case headlines but are not part of a road name.
_STOP = {
    "the", "on", "at", "in", "near", "along", "of", "to", "from", "via", "and", "for", "after", "before", "over",
    "traffic", "jam", "jams", "accident", "accidents", "crash", "closed", "closure", "shut", "blocked", "block",
    "diverted", "diversion", "diversions", "new", "old", "stretch", "section", "lane", "lanes", "km", "toll",
    "landslide", "flood", "flooding", "rain", "rains", "heavy", "major", "massive", "long", "hours", "stuck",
    "snarl", "snarls", "vehicles", "truck", "bus", "car", "pileup", "fire", "work", "works", "repair", "repairs",
    "today", "tomorrow", "update", "updates", "live", "breaking", "advisory", "police", "nhai", "msrdc",
    "elevated", "service", "road", "roads", "highway", "highways", "expressway", "expressways", "express",
    "commuters", "motorists", "restrictions", "restriction", "ban", "banned", "movement", "vip", "protest",
    "why", "this", "that", "these", "your", "our", "its", "it", "how", "what", "who", "will", "is", "are", "was",
    "were", "has", "have", "can", "fix", "fixed", "amid", "as", "with", "by", "now", "soon", "finally", "here",
    "all", "every", "says", "said", "proposed", "upcoming", "under", "construction",
    "ease", "eases", "crore", "crores", "lakh", "worsens", "worsen", "waterlogged", "hit", "hits", "first", "second",
    "third", "urban", "rural", "smooth", "smoother", "faster", "safer", "safety", "speed", "speeding", "deadly",
    "killer", "busy", "busiest", "longest", "newest", "opens", "opened", "inaugurated", "inaugurates", "launch",
    "launched", "project", "plan", "plans", "cost", "costs", "worth", "entire", "whole", "key", "crucial", "big",
    "damaged", "cracked", "cracks", "sinks", "caves", "collapsed", "mishap", "mishaps", "greenfield", "access",
    "controlled", "six", "eight", "four", "lane", "elevated", "link", "missing", "launches", "city",
}
# Abbreviations used in headlines for cities on highway names.
_ABBREV = {"mum": "Mumbai", "del": "Delhi", "lko": "Lucknow", "jmu": "Jammu", "sgr": "Srinagar", "ahd": "Ahmedabad",
           "blr": "Bengaluru", "hyd": "Hyderabad", "bom": "Mumbai", "pnq": "Pune"}
_TOKEN = r"[A-Z][A-Za-z]+(?:\s*[-–]\s*[A-Z][A-Za-z]+)*"
_EXPRESSWAY = re.compile(rf"((?:{_TOKEN}\s+){{0,3}})(Expressway|Express\s+Highway|Express\s+Way)\b", re.I)
_PAIR_HIGHWAY = re.compile(r"\b([A-Z][A-Za-z]+(?:\s*[-–]\s*[A-Z][A-Za-z]+)+)\s+(?:National\s+|State\s+)?Highway\b",
                           re.I)
_CITY_CASE = {c.lower(): c for c in CITIES}
_KNOWN_PLACES = set(_CITY_CASE)
_SEVERITY_RANK = {"UNKNOWN": 0, "LOW": 1, "MODERATE": 2, "HIGH": 3, "CRITICAL": 4}


@dataclass(frozen=True)
class HighwayRef:
    id: str     # stable key, e.g. "NH-48", "SH-10|Maharashtra", "EXP:mumbai-pune-expressway"
    name: str   # display name
    type: str   # NATIONAL_HIGHWAY / STATE_HIGHWAY / EXPRESSWAY / NAMED_HIGHWAY


def _title_tokens(words: str) -> list[str]:
    """Split a captured name into tokens, keeping hyphenated pairs together."""
    words = re.sub(r"\s*[-–]\s*", "-", words.strip())
    return [w for w in words.split() if w]


def _is_place(p: str) -> bool:
    low = p.lower()
    return low in _KNOWN_PLACES or low in ALIASES or low in _ABBREV


def _canon_part(p: str) -> str:
    low = p.lower()
    if low in _ABBREV:
        return _ABBREV[low]
    if low in ALIASES or low in _KNOWN_PLACES:
        return ALIASES.get(low) or _CITY_CASE[low]  # "Bangalore" -> "Bengaluru", "Gurgaon" -> "Gurugram"
    if p.islower() or (p.isupper() and len(p) > 5):
        return p[:1].upper() + p[1:].lower()
    return p  # keep acronyms such as PVNR


def _clean_name(prefix: str) -> tuple[str, str] | None:
    """(display name, order-independent key) of the words preceding a road keyword, or None."""
    tokens = _title_tokens(prefix)
    kept: list[list[str]] = []
    for pos, tok in enumerate(reversed(tokens)):  # walk back from the road keyword
        parts = [p for p in tok.split("-") if p]
        if not parts or any(p.lower() in _STOP for p in parts):
            break
        known = [_is_place(p) for p in parts]
        if len(parts) > 1:
            if not any(known):  # "Hell-Hole", "Pothole-Ridden"
                break
            if sum(known) >= 2:  # "Setu-Mumbai-Pune" -> "Mumbai-Pune"
                first, last = known.index(True), len(known) - 1 - known[::-1].index(True)
                parts, known = parts[first:last + 1], known[first:last + 1]
        elif not known[0]:
            # An unknown single word is accepted only directly before the keyword
            # ("Yamuna Expressway", "Western Express Highway"), never further back.
            if pos > 0 or not tok[0].isupper():
                break
        kept.insert(0, [_canon_part(p) for p in parts])
        if len(kept) == 3:
            break
    if not kept:
        return None
    if len(kept) > 1 and len(kept[-1]) == 1 and not _is_place(kept[-1][0]):
        kept = kept[-1:]  # "Delhi-Agra Yamuna", "Mumbai Western" -> "Yamuna", "Western"
    paired = [i for i, parts in enumerate(kept) if len(parts) > 1]
    if paired:  # "Missing Link Mumbai-Pune" -> "Mumbai-Pune"
        kept = kept[paired[-1]:]
    elif len(kept) > 1 and all(len(parts) == 1 and _is_place(parts[0]) for parts in kept):
        kept = [[parts[0] for parts in kept]]  # "Pune Mumbai Expressway" -> "Pune-Mumbai"
    display = " ".join("-".join(parts) for parts in kept)
    if len(kept) == 1 and len(kept[0]) > 1 and all(_is_place(p) for p in kept[0]):
        key = "-".join(sorted(p.lower() for p in kept[0]))  # Mumbai-Pune == Pune-Mumbai
    else:
        key = display.lower()
    return display, key


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def extract_highways(text: str, state: str | None = None) -> list[HighwayRef]:
    """Highway references stated in ``text`` (deduplicated, in order of appearance)."""
    if not text:
        return []
    found: dict[str, HighwayRef] = {}
    for m in _NUMBERED.finditer(text):
        kind = m.group(1).upper().replace(".", "").replace(" ", "")
        num = m.group(2).upper()
        if kind in ("NH", "NATIONALHIGHWAY"):
            ref = HighwayRef(f"NH-{num}", f"NH-{num}", "NATIONAL_HIGHWAY")
        else:
            key = f"SH-{num}|{state}" if state else f"SH-{num}"
            ref = HighwayRef(key, f"SH-{num}" + (f" ({state})" if state else ""), "STATE_HIGHWAY")
        found.setdefault(ref.id, ref)
    for m in _EXPRESSWAY.finditer(text):
        named = _clean_name(m.group(1))
        if not named:
            continue
        suffix = "Express Highway" if "highway" in m.group(2).lower() else "Expressway"
        key = f"EXP:{_slug(named[1] + ' ' + suffix)}"
        found.setdefault(key, HighwayRef(key, f"{named[0]} {suffix}", "EXPRESSWAY"))
    for m in _PAIR_HIGHWAY.finditer(text):
        named = _clean_name(m.group(1))
        if not named or "-" not in named[0]:
            continue
        key = f"HWY:{_slug(named[1] + ' highway')}"
        found.setdefault(key, HighwayRef(key, f"{named[0]} Highway", "NAMED_HIGHWAY"))
    return list(found.values())


def mask_highway_names(text: str) -> str:
    """Blank out named highways/expressways so their place names ("Mumbai-Goa Highway") are not read as the
    location of the event."""
    out = text or ""
    for pattern in (_EXPRESSWAY, _PAIR_HIGHWAY):
        out = pattern.sub(lambda m: " " * len(m.group(0)) if _clean_name(m.group(1)) else m.group(0), out)
    return out


def primary_highway_number(text: str) -> str | None:
    """First numbered highway (``NH-48`` / ``SH-10``) stated in the text, for the highway_number field."""
    for ref in extract_highways(text):
        if ref.type in ("NATIONAL_HIGHWAY", "STATE_HIGHWAY"):
            return ref.name.split(" (")[0]
    return None


def primary_named_road(text: str) -> str | None:
    for ref in extract_highways(text):
        if ref.type in ("EXPRESSWAY", "NAMED_HIGHWAY"):
            return ref.name
    return None


# ----------------------------------------------------------------------------- aggregation
def _new_bucket(ref: HighwayRef) -> dict:
    return {"id": ref.id, "name": ref.name, "type": ref.type, "running_incidents": 0, "stale_incidents": 0,
            "unverified_reports": 0, "categories": {}, "max_severity": "UNKNOWN", "states": set(), "cities": set(),
            "last_reported_at": None, "incident_ids": [], "report_ids": []}


def _touch(b: dict, *, state, city, when, category=None, severity=None) -> None:
    if state:
        b["states"].add(state)
    if city:
        b["cities"].add(city)
    if when and (b["last_reported_at"] is None or when > b["last_reported_at"]):
        b["last_reported_at"] = when
    if category:
        b["categories"][category] = b["categories"].get(category, 0) + 1
    if severity and _SEVERITY_RANK.get(severity, 0) > _SEVERITY_RANK.get(b["max_severity"], 0):
        b["max_severity"] = severity


def collect(db: Session, *, report_days: int = 7, include_reports: bool = True, include_stale: bool = True) -> dict[str, dict]:
    """Highways with possibly running events, keyed by highway id."""
    stale_hours = int(settings_store.get(db, "incidents").get("stale_after_hours", 72))
    buckets: dict[str, dict] = {}

    incs = db.scalars(select(Incident).where(Incident.status.in_(inc_svc.ACTIVE_STATUSES),
                                             or_(Incident.time_status.is_(None), Incident.time_status != "RESOLVED"))).all()
    titles: dict[str, list[str]] = {}
    if incs:
        ids = [i.id for i in incs]
        for chunk in range(0, len(ids), 500):
            for inc_id, title in db.execute(select(Article.incident_id, Article.title).where(
                    Article.incident_id.in_(ids[chunk:chunk + 500]), Article.review_status != "REJECTED")):
                titles.setdefault(inc_id, []).append(title or "")
    for inc in incs:
        stale = inc_svc.is_stale(inc, stale_hours)
        if stale and not include_stale:
            continue
        text = " \n".join([inc.highway_number or "", inc.road_name or "", inc.title or "", *titles.get(inc.id, [])])
        for ref in extract_highways(text, inc.state):
            b = buckets.setdefault(ref.id, _new_bucket(ref))
            b["stale_incidents" if stale else "running_incidents"] += 1
            b["incident_ids"].append(inc.id)
            _touch(b, state=inc.state, city=inc.city, when=inc.last_reported_at, category=inc.category,
                   severity=inc.severity)

    if include_reports:
        since = utcnow() - timedelta(days=max(1, report_days))
        rel = select(Classification.relevance).where(Classification.id == Article.current_classification_id) \
            .correlate(Article).scalar_subquery()
        q = select(Article).where(Article.incident_id.is_(None), Article.review_status != "REJECTED",
                                  Article.prefilter_label.in_(("LIKELY_RELEVANT", "POSSIBLY_RELEVANT")),
                                  or_(Article.published_at >= since,
                                      (Article.published_at.is_(None)) & (Article.ingested_at >= since)),
                                  or_(Article.current_classification_id.is_(None), rel.in_(("RELEVANT", "NEEDS_REVIEW"))))
        for art in db.scalars(q.limit(20000)):
            city, state = normalize_city(art.query_city) if art.query_city else (None, None)
            for ref in extract_highways(art.title or "", state):
                b = buckets.setdefault(ref.id, _new_bucket(ref))
                b["unverified_reports"] += 1
                b["report_ids"].append(art.id)
                _touch(b, state=None, city=None, when=art.published_at or art.ingested_at)
    return buckets


def summarize(b: dict) -> dict:
    out = {k: v for k, v in b.items() if k not in ("incident_ids", "report_ids")}
    out["states"], out["cities"] = sorted(b["states"]), sorted(b["cities"])
    out["total"] = b["running_incidents"] + b["stale_incidents"] + b["unverified_reports"]
    return out
