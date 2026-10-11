"""Persistent, non-secret application settings stored in the database."""
from __future__ import annotations

import copy
from typing import Any

from sqlalchemy.orm import Session

from ..db.models import AppSetting, utcnow

CATEGORIES = [
    ("ACCIDENT", "Accident / vehicle incident"),
    ("CONGESTION", "Congestion / major delay"),
    ("CLOSURE", "Road or highway closure"),
    ("DIVERSION", "Traffic diversion"),
    ("FLOODING", "Flooding / waterlogging"),
    ("LANDSLIDE", "Landslide"),
    ("PROTEST", "Protest / rally / strike / blockade"),
    ("CONSTRUCTION", "Construction / maintenance"),
    ("WEATHER", "Weather-related disruption"),
    ("INFRASTRUCTURE", "Infrastructure damage"),
    ("SECURITY_VIP", "Security / VIP movement"),
    ("OTHER", "Other"),
    ("UNKNOWN", "Unknown"),
]

DEFAULTS: dict[str, Any] = {
    "branding": {
        "company_name": "Aviral Consulting (OPC) Private Limited",
        "company_location": "Mumbai, Maharashtra, India",
        "product_name": "Road Disruption Intelligence",
        "product_short_name": "RDI",
        "logo_url": "",
        "support_email": "",
        "website": "",
    },
    "llm": {
        "active_provider": "ollama",
        "fallback_provider": "",
        "providers": {
            "ollama": {"base_url": "http://127.0.0.1:11434", "model": "llama3:8b", "temperature": 0.0,
                       "max_tokens": 900, "timeout_seconds": 120},
            "openai_compatible": {"base_url": "https://api.openai.com/v1", "model": "gpt-4o-mini",
                                  "temperature": 0.0, "max_tokens": 900, "timeout_seconds": 60,
                                  "structured_output": "json_schema", "label": "OpenAI / compatible"},
            "anthropic": {"base_url": "https://api.anthropic.com", "model": "claude-haiku-5-5",
                          "temperature": 0.0, "max_tokens": 900, "timeout_seconds": 60},
        },
        "last_tests": {},
    },
    "classification": {
        "auto_classify_new": False,
        "auto_classify_min_prefilter": "LIKELY_RELEVANT",
        "max_input_chars": 4000,
        "concurrency": 1,
        "retries": 2,
        "review_low_confidence": True,
        "review_unverified_evidence": True,
        "review_unresolved_location": True,
        "review_headline_only": False,
        "categories": [c for c, _ in CATEGORIES],
    },
    "incidents": {
        "stale_after_hours": 72,
        "link_window_hours": 72,
        "auto_resolve_on_report": True,
    },
    "alerts": {
        "enabled": True,
        "min_severity": "HIGH",
        "on_status": ["CONFIRMED"],
        "categories": [],
    },
    "map": {
        "style_url": "https://tiles.openfreemap.org/styles/positron",
        "attribution_note": "Basemap: OpenFreeMap, map data © OpenStreetMap contributors",
        "default_center": [22.5, 79.0],
        "default_zoom": 4.3,
        "focus_regions": {"Mumbai": [19.076, 72.8777, 10.5], "Delhi NCR": [28.6139, 77.209, 9.5],
                          "Pune": [18.5204, 73.8567, 10.5], "Bengaluru": [12.9716, 77.5946, 10.5],
                          "Chennai": [13.0827, 80.2707, 10.5], "Kolkata": [22.5726, 88.3639, 10.5],
                          "Hyderabad": [17.385, 78.4867, 10.5]},
    },
    "acquisition": {
        "default_poll_minutes": 180,
        "min_poll_minutes": 30,
    },
    "setup": {"completed_steps": [], "dismissed": False},
}


def _merge(base: Any, override: Any) -> Any:
    if isinstance(base, dict) and isinstance(override, dict):
        out = dict(base)
        for k, v in override.items():
            out[k] = _merge(base.get(k), v) if k in base else v
        return out
    return copy.deepcopy(override) if override is not None else copy.deepcopy(base)


def get(db: Session, key: str) -> Any:
    row = db.get(AppSetting, key)
    default = copy.deepcopy(DEFAULTS.get(key))
    if row is None:
        return default
    if isinstance(default, dict):
        return _merge(default, row.value or {})
    return row.value


def put(db: Session, key: str, value: Any) -> Any:
    if key not in DEFAULTS:
        raise KeyError(key)
    row = db.get(AppSetting, key)
    if row is None:
        row = AppSetting(key=key, value=value)
        db.add(row)
    else:
        row.value = value
        row.updated_at = utcnow()
    db.flush()
    return get(db, key)


def patch(db: Session, key: str, partial: dict) -> Any:
    current = get(db, key)
    merged = _merge(current, partial)
    return put(db, key, merged)
