"""Deterministic keyword pre-filter.

This is NOT a classification. It only prioritises which records are worth
sending to the LLM classifier and is shown in the UI as "keyword pre-filter".
"""
from __future__ import annotations

import re
from dataclasses import dataclass

STRONG = [
    "road closure", "road closed", "roads closed", "road blocked", "highway blocked", "highway closed",
    "traffic diversion", "traffic diverted", "diversions", "route diverted", "traffic restrictions",
    "traffic restricted", "traffic advisory", "traffic jam", "traffic snarl", "gridlock", "waterlogging",
    "waterlogged", "landslide", "bridge collapse", "road cave-in", "cave-in", "chakka jam", "rasta roko",
    "road blockade", "nh closed", "expressway closed", "flyover closed", "traffic curbs", "pileup",
    "vehicles stranded", "traffic halted", "traffic suspended", "road washed away",
]
WEAK = [
    "traffic", "accident", "crash", "collision", "flood", "procession", "protest", "rally", "strike",
    "vip movement", "construction", "repair work", "pothole", "highway", "expressway", "flyover",
    "bridge", "detour", "congestion", "fog", "heavy rain", "rainfall", "blockade", "bandh",
    "closed", "shut", "blocked", "diverted", "overturned", "overturns", "stranded", "jam", "pile-up",
]
# Highway/road designation followed by a disruption verb, e.g. "NH-48 closed", "SH 10 blocked".
STRONG_PATTERNS = [
    re.compile(r"\b(nh|sh|national highway|state highway|expressway|highway|ghat|road)\b\s*[-–]?\s*\d*[a-z]?"
               r"[^.]{0,40}?\b(closed|shut|blocked|blockade|diverted|submerged|washed away|caved in|cave-in)\b"),
]
NEGATIVE = [
    "stock market", "sensex", "nifty", "box office", "cricket score", "ipl auction", "recipe",
    "horoscope", "web series", "trailer", "real estate project", "property prices", "flats for sale",
]

_WORD = lambda kw: re.compile(r"(?<![a-z])" + re.escape(kw) + r"(?![a-z])")  # noqa: E731
_STRONG_RE = [(_WORD(k), k) for k in STRONG]
_WEAK_RE = [(_WORD(k), k) for k in WEAK]
_NEG_RE = [(_WORD(k), k) for k in NEGATIVE]

METHOD = "keyword_prefilter_v2"


@dataclass
class PrefilterResult:
    label: str  # LIKELY_RELEVANT / POSSIBLY_RELEVANT / UNLIKELY
    score: float
    reason: str


def assess(title: str, text: str = "") -> PrefilterResult:
    blob = f"{title or ''} {text or ''}".lower()
    strong = [k for r, k in _STRONG_RE if r.search(blob)]
    strong += [m.group(0)[:40] for p in STRONG_PATTERNS for m in [p.search(blob)] if m]
    weak = [k for r, k in _WEAK_RE if r.search(blob)]
    neg = [k for r, k in _NEG_RE if r.search(blob)]
    if neg and not strong:
        return PrefilterResult("UNLIKELY", 0.05, f"Off-topic terms: {', '.join(neg[:3])}")
    if strong:
        return PrefilterResult("LIKELY_RELEVANT", min(1.0, 0.7 + 0.1 * len(strong)),
                               f"Strong terms: {', '.join(strong[:4])}")
    if len(weak) >= 2:
        return PrefilterResult("POSSIBLY_RELEVANT", 0.5, f"Related terms: {', '.join(weak[:4])}")
    if len(weak) == 1:
        return PrefilterResult("POSSIBLY_RELEVANT", 0.3, f"Single related term: {weak[0]}")
    return PrefilterResult("UNLIKELY", 0.0, "No road-disruption terms found")
