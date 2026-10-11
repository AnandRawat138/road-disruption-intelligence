"""Classification output schema, prompt and validation.

The model is asked for a flat JSON object. Its output is validated and
normalised before anything is stored; extraction problems are recorded as
validation issues instead of being silently converted into success.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta
from difflib import SequenceMatcher

from ..settings_store import CATEGORIES
from ..text import parse_timestamp

PROMPT_VERSION = "v1.1"

RELEVANCE = ["RELEVANT", "RELATED", "IRRELEVANT", "NEEDS_REVIEW"]
CATEGORY_CODES = [c for c, _ in CATEGORIES]
TIME_STATUS = ["ONGOING", "UPCOMING", "RESOLVED", "UNKNOWN"]
SEVERITY = ["LOW", "MODERATE", "HIGH", "CRITICAL", "UNKNOWN"]
CONFIDENCE = ["LOW", "MEDIUM", "HIGH"]

_NULLABLE = {"type": ["string", "null"]}

OUTPUT_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "relevance": {"type": "string", "enum": RELEVANCE},
        "category": {"type": "string", "enum": CATEGORY_CODES},
        "summary": {"type": "string"},
        "country": _NULLABLE, "state": _NULLABLE, "city": _NULLABLE, "locality": _NULLABLE,
        "road_name": _NULLABLE, "highway_number": _NULLABLE, "direction": _NULLABLE, "affected_segment": _NULLABLE,
        "event_start": _NULLABLE, "event_end": _NULLABLE,
        "time_status": {"type": "string", "enum": TIME_STATUS},
        "severity": {"type": "string", "enum": SEVERITY},
        "reported_delay": _NULLABLE, "advisory_action": _NULLABLE,
        "evidence_excerpt": _NULLABLE,
        "confidence": {"type": "string", "enum": CONFIDENCE},
        "missing_information": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["relevance", "category", "summary", "time_status", "severity", "confidence", "evidence_excerpt",
                 "country", "state", "city", "locality", "road_name", "highway_number", "event_start", "event_end"],
}

SYSTEM_PROMPT = """You are a careful road-disruption intelligence analyst for India.
You read one news record and return ONE JSON object that follows the provided schema.

Strict rules:
- Use ONLY information stated in the record. Never guess or invent road names, highway numbers,
  places, dates, times, durations, delays or severity. If something is not stated, use null
  (or UNKNOWN for enums).
- relevance:
  RELEVANT = the record reports a specific road/traffic disruption in India (closure, diversion,
    accident affecting traffic, congestion, waterlogging, landslide, protest/blockade, VIP movement
    restrictions, construction affecting traffic, infrastructure damage, weather disruption).
    Traffic advisories, announced or planned restrictions, closures and diversions (for festivals, visits,
    protests or works) ARE RELEVANT even if they start in the future.
  RELATED = transport news without a specific disruption (policy, projects, general statistics).
  IRRELEVANT = not about road transport in India (including events outside India).
  NEEDS_REVIEW = genuinely ambiguous.
- category: the single best event category. Definitions:
  ACCIDENT = crash/collision/vehicle fire/overturned vehicle; CONGESTION = traffic jam, gridlock, long delays;
  CLOSURE = a road, lane, bridge, flyover or highway is closed or vehicles are banned;
  DIVERSION = traffic diverted/rerouted or restrictions announced (including for festivals, processions,
  rallies, matches or events); FLOODING = flooding or waterlogging of roads; LANDSLIDE = landslide/rockfall;
  PROTEST = protest, rally, strike, bandh, rasta roko or blockade; CONSTRUCTION = road works, repairs, metro or
  flyover construction affecting traffic; WEATHER = rain, fog, snow, heat or cyclone affecting travel (not
  flooding); INFRASTRUCTURE = road cave-in, bridge collapse, potholes or other damage; SECURITY_VIP = VIP/PM/
  minister visits, security restrictions or motorcades. If both a closure and diversions are announced, prefer
  CLOSURE. Use OTHER only when none of these applies; UNKNOWN if the record is too vague.
- event_start / event_end: ISO 8601 (e.g. 2026-09-08T10:00:00+05:30) ONLY when the record states the
  date/time. Resolve relative words such as "today" or "tomorrow" against the publication date. Otherwise null.
- time_status: as described in the record at publication time (not today's date):
  UPCOMING = a planned/announced future disruption; ONGOING = currently in effect;
  RESOLVED = ONLY if the record explicitly says traffic was restored, the road reopened or cleared;
  UNKNOWN otherwise. Diversions "issued" or "in place" are ONGOING, not RESOLVED.
- state: an Indian state or union territory name only (never a road or city name).
- summary: one factual sentence describing the disruption.
- severity: LOW, MODERATE, HIGH or CRITICAL only when supported by the record (e.g. deaths, full closure of a
  highway, city-wide gridlock = HIGH/CRITICAL); otherwise UNKNOWN.
- highway_number: e.g. "NH-48", "SH-10" only if written in the record.
- evidence_excerpt: copy the shortest exact sentence or phrase from the record that supports the
  classification (verbatim, no paraphrase). null if the record has no supporting text.
- advisory_action: a short, practical operator suggestion only if the record supports it (e.g. "avoid X,
  use Y as stated by police"); otherwise null.
- confidence: your own LOW/MEDIUM/HIGH judgement of how well the record supports your answer.
  Headline-only records rarely deserve HIGH.
- missing_information: list the important fields the record does not state.
Return JSON only."""


def build_user_prompt(title: str, source: str | None, published: datetime | None, retrieved: datetime | None,
                      body: str, max_chars: int) -> str:
    body = (body or "").strip()
    if len(body) > max_chars:
        body = body[:max_chars] + " [truncated]"
    lines = [
        f"Title: {title}",
        f"Source: {source or 'unknown'}",
        f"Published (UTC): {published.isoformat() if published else 'unknown'}",
        f"Retrieved (UTC): {retrieved.isoformat() if retrieved else 'unknown'}",
        "Text:",
        body or "(no text beyond the title)",
    ]
    return "\n".join(lines)


# --------------------------------------------------------------------------- normalisation
_NULL_STRINGS = {"", "null", "none", "unknown", "n/a", "na", "not mentioned", "not specified", "not stated",
                 "unspecified", "not available", "-"}

CATEGORY_SYNONYMS = {
    "FLOOD": "FLOODING", "WATERLOGGING": "FLOODING", "FLOODING/WATERLOGGING": "FLOODING", "RAIN": "WEATHER",
    "TRAFFIC_JAM": "CONGESTION", "TRAFFIC": "CONGESTION", "JAM": "CONGESTION", "HEAVY_TRAFFIC": "CONGESTION",
    "ROAD_CLOSURE": "CLOSURE", "FULL_CLOSURE": "CLOSURE", "PARTIAL_CLOSURE": "CLOSURE",
    "TRAFFIC_DIVERSION": "DIVERSION", "VIP_MOVEMENT": "SECURITY_VIP", "SECURITY": "SECURITY_VIP", "VIP": "SECURITY_VIP",
    "RALLY": "PROTEST", "STRIKE": "PROTEST", "BLOCKADE": "PROTEST", "PROTEST/BLOCKADE": "PROTEST",
    "ROAD_SHOW": "PROTEST", "MAINTENANCE": "CONSTRUCTION", "CONSTRUCTION/MAINTENANCE": "CONSTRUCTION",
    "INFRASTRUCTURE_DAMAGE": "INFRASTRUCTURE", "COLLAPSE": "INFRASTRUCTURE", "CRASH": "ACCIDENT",
    "WEATHER_DISRUPTION": "WEATHER", "FOG": "WEATHER", "SECURITY/VIP_MOVEMENT": "SECURITY_VIP",
}

STRING_LIMITS = {"summary": 600, "country": 60, "state": 80, "city": 100, "locality": 200, "road_name": 200,
                 "highway_number": 40, "direction": 100, "affected_segment": 400, "reported_delay": 200,
                 "advisory_action": 400, "evidence_excerpt": 800}


def extract_json(raw: str) -> dict | None:
    if raw is None:
        return None
    s = raw.strip()
    s = re.sub(r"^```(?:json)?\s*", "", s)
    s = re.sub(r"\s*```$", "", s)
    try:
        obj = json.loads(s)
        return obj if isinstance(obj, dict) else None
    except json.JSONDecodeError:
        pass
    start, end = s.find("{"), s.rfind("}")
    if start != -1 and end > start:
        try:
            obj = json.loads(s[start:end + 1])
            return obj if isinstance(obj, dict) else None
        except json.JSONDecodeError:
            return None
    return None


def _clean_str(v, limit: int) -> str | None:
    if v is None:
        return None
    if isinstance(v, (list, tuple)):
        v = ", ".join(str(x) for x in v if x not in (None, ""))
    s = re.sub(r"\s+", " ", str(v)).strip().strip('"')
    if s.lower() in _NULL_STRINGS:
        return None
    return s[:limit]


def _enum(v, allowed: list[str], synonyms: dict | None = None) -> str | None:
    if v is None:
        return None
    s = re.sub(r"[\s\-]+", "_", str(v).strip().upper())
    if synonyms and s in synonyms:
        s = synonyms[s]
    return s if s in allowed else None


def normalize_highway(v: str | None) -> str | None:
    if not v:
        return None
    s = v.upper().replace("NATIONAL HIGHWAY", "NH").replace("STATE HIGHWAY", "SH")
    m = re.search(r"\b(NH|SH|MDR)\s*[-–]?\s*(\d{1,4}[A-Z]?)\b", s)
    if m:
        return f"{m.group(1)}-{m.group(2)}"
    return v.strip()[:40]


def _norm_text(s: str) -> str:
    return re.sub(r"[^\w]+", " ", (s or "").lower()).strip()


def appears_in(needle: str | None, haystack: str) -> bool:
    if not needle:
        return False
    n, h = _norm_text(needle), _norm_text(haystack)
    if not n:
        return False
    if n in h:
        return True
    tokens = [t for t in n.split() if len(t) > 2]
    if not tokens:
        return False
    hits = sum(1 for t in tokens if t in h.split())
    return hits / len(tokens) >= 0.8


def evidence_check(excerpt: str | None, source: str) -> tuple[bool, str]:
    if not excerpt:
        return False, "missing"
    n, h = _norm_text(excerpt), _norm_text(source)
    if n and n in h:
        return True, "verbatim"
    if len(n) > 10:
        # best fuzzy match over sliding windows of the same length
        words, nwords = h.split(), n.split()
        best = 0.0
        w = len(nwords)
        for i in range(0, max(1, len(words) - w + 1)):
            best = max(best, SequenceMatcher(None, n, " ".join(words[i:i + w])).ratio())
            if best >= 0.9:
                break
        if best >= 0.9:
            return True, "near_verbatim"
    return False, "not_found_in_source"


def _highway_in_text(hw: str, source: str) -> bool:
    m = re.match(r"(NH|SH|MDR)-(\w+)", hw)
    if not m:
        return appears_in(hw, source)
    num = m.group(2)
    return re.search(rf"\b(NH|SH|MDR|national highway|state highway|highway)\s*[-–]?\s*(no\.?\s*)?{re.escape(num)}\b",
                     source, re.I) is not None


def validate_output(raw: dict, source_text: str, published: datetime | None) -> tuple[dict, list[str], list[str]]:
    """Validate and normalise a parsed model output.

    Returns (normalised fields, validation issues, fatal errors).
    """
    issues: list[str] = []
    fatal: list[str] = []
    out: dict = {}

    rel = _enum(raw.get("relevance"), RELEVANCE)
    if rel is None:
        fatal.append(f"invalid or missing relevance: {raw.get('relevance')!r}")
    out["relevance"] = rel

    cat = _enum(raw.get("category"), CATEGORY_CODES, CATEGORY_SYNONYMS)
    if cat is None:
        if raw.get("category") not in (None, ""):
            issues.append(f"unknown category {raw.get('category')!r} mapped to UNKNOWN")
        cat = "UNKNOWN"
    out["category"] = cat

    for key, limit in STRING_LIMITS.items():
        out[key] = _clean_str(raw.get(key), limit)

    out["highway_number"] = normalize_highway(out["highway_number"])
    if out["highway_number"] and not _highway_in_text(out["highway_number"], source_text):
        issues.append(f"highway {out['highway_number']} not found in the source text – removed")
        out["highway_number"] = None
    if out["road_name"] and not appears_in(out["road_name"], source_text):
        issues.append(f"road name '{out['road_name']}' not found in the source text – removed")
        out["road_name"] = None
    for loc_key in ("locality", "city"):
        if out[loc_key] and not appears_in(out[loc_key], source_text):
            issues.append(f"{loc_key} '{out[loc_key]}' is inferred (not stated verbatim)")

    out["time_status"] = _enum(raw.get("time_status"), TIME_STATUS) or "UNKNOWN"
    out["severity"] = _enum(raw.get("severity"), SEVERITY) or "UNKNOWN"
    conf = raw.get("confidence")
    if isinstance(conf, (int, float)):
        conf = "HIGH" if conf >= 0.8 else "MEDIUM" if conf >= 0.5 else "LOW"
    out["model_confidence"] = _enum(conf, CONFIDENCE) or "LOW"
    if _enum(conf, CONFIDENCE) is None:
        issues.append("confidence missing or invalid – treated as LOW")

    for key in ("event_start", "event_end"):
        val = raw.get(key)
        dt = None
        if val not in (None, "") and str(val).strip().lower() not in _NULL_STRINGS:
            dt = parse_timestamp(val)
            if dt is None:
                issues.append(f"{key} '{str(val)[:40]}' is not a valid date – removed")
            elif published and abs(dt - published) > timedelta(days=400):
                issues.append(f"{key} {dt.date()} is implausibly far from the publication date – removed")
                dt = None
        out[key] = dt
    if out["event_start"] and out["event_end"] and out["event_end"] < out["event_start"]:
        issues.append("event_end is before event_start")

    missing = raw.get("missing_information")
    out["missing_fields"] = [str(m)[:80] for m in missing][:15] if isinstance(missing, list) else []

    ignored = [k for k in raw.keys() if k in ("latitude", "longitude", "lat", "lon", "coordinates")]
    if ignored:
        issues.append("model-supplied coordinates ignored (coordinates come from the geocoder only)")

    ok, how = evidence_check(out["evidence_excerpt"], source_text)
    out["evidence_verified"] = ok
    if not ok and rel in ("RELEVANT", "NEEDS_REVIEW"):
        issues.append("evidence excerpt " + ("missing" if how == "missing" else "not found verbatim in the source"))
    return out, issues, fatal
