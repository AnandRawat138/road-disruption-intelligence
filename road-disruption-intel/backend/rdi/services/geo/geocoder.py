"""Geocoding with an offline gazetteer, a persistent cache and rate-limited Nominatim.

Every result records *how* it was obtained and at what precision. Results are
never presented as exact incident coordinates:

* ``APPROXIMATE`` – centroid of a locality, city or state.
* ``MANUAL``      – placed by an operator.
* ``UNRESOLVED``  – no trustworthy location.
"""
from __future__ import annotations

import logging
import math
import re
import threading
import time
from dataclasses import asdict, dataclass

import httpx
from sqlalchemy.orm import Session

from ...config import settings
from ...db.models import GeocodeCache, utcnow
from ...db.session import SessionLocal
from .gazetteer_data import ALIASES, CITIES, STATE_ALIASES, STATES

log = logging.getLogger(__name__)

_CITY_INDEX = {k.lower(): k for k in CITIES}
_STATE_INDEX = {k.lower(): k for k in STATES}
_nominatim_lock = threading.Lock()
_last_call = [0.0]
MIN_INTERVAL = 1.1  # Nominatim usage policy: max 1 request per second
MAX_CITY_DISTANCE_KM = 60.0


@dataclass
class GeoResult:
    status: str  # APPROXIMATE / MANUAL / UNRESOLVED
    latitude: float | None = None
    longitude: float | None = None
    precision: str | None = None  # LOCALITY / CITY / STATE / MANUAL
    method: str | None = None  # GAZETTEER / NOMINATIM / MANUAL
    query: str | None = None
    display_name: str | None = None
    confidence: str = "NONE"  # HIGH / MEDIUM / LOW / NONE
    note: str | None = None

    def as_dict(self) -> dict:
        return asdict(self)


def _clean(s: str | None) -> str:
    return re.sub(r"\s+", " ", (s or "").strip())


def normalize_state(name: str | None) -> str | None:
    n = _clean(name).lower().rstrip(".")
    if not n or n in ("unknown", "null", "none", "n/a"):
        return None
    n = STATE_ALIASES.get(n, n)
    return _STATE_INDEX.get(n.lower())  # only recognised Indian states/UTs are accepted


def normalize_city(name: str | None) -> tuple[str | None, str | None]:
    """Return (canonical city, state) – state is None when the city is not in the gazetteer."""
    n = _clean(name)
    if not n or n.lower() in ("unknown", "null", "none", "n/a", "not mentioned", "national highway"):
        return None, None
    low = n.lower()
    canon = ALIASES.get(low) or _CITY_INDEX.get(low)
    if canon:
        return canon, CITIES[canon][0]
    return n, None


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def valid_india_coords(lat, lon) -> bool:
    try:
        lat, lon = float(lat), float(lon)
    except (TypeError, ValueError):
        return False
    return 6.0 <= lat <= 37.6 and 68.0 <= lon <= 97.5


class Geocoder:
    def __init__(self, db: Session, client: httpx.Client | None = None, online: bool | None = None):
        self.db = db
        self.client = client
        self.online = settings.geocoding_online if online is None else online

    # ------------------------------------------------------------------ public
    def resolve(self, locality: str | None, city: str | None, state: str | None) -> GeoResult:
        city_c, city_state = normalize_city(city)
        state_c = normalize_state(state) or city_state
        locality = _clean(locality)

        city_point = None
        if city_c and city_c in CITIES:
            _, lat, lon = CITIES[city_c]
            city_point = (lat, lon)

        if locality and self.online and (city_c or state_c):
            q = ", ".join(x for x in (locality, city_c, state_c, "India") if x)
            hit = self._nominatim(q)
            if hit and hit.status == "APPROXIMATE":
                if city_point and haversine_km(city_point[0], city_point[1], hit.latitude, hit.longitude) > MAX_CITY_DISTANCE_KM:
                    log.info("Rejected Nominatim match for %r: too far from %s", q, city_c)
                else:
                    hit.precision = "LOCALITY"
                    hit.confidence = "MEDIUM"
                    hit.note = "Centroid of the named locality – the exact incident position is not known."
                    return hit

        if city_point:
            return GeoResult("APPROXIMATE", city_point[0], city_point[1], "CITY", "GAZETTEER", city_c,
                             f"{city_c}, {CITIES[city_c][0]}", "LOW",
                             "City centroid – the incident is somewhere in or near this city.")

        if city_c and self.online:
            q = ", ".join(x for x in (city_c, state_c, "India") if x)
            hit = self._nominatim(q)
            if hit and hit.status == "APPROXIMATE":
                hit.precision = "CITY"
                hit.confidence = "LOW"
                hit.note = "Centroid of the named place – the incident position is approximate."
                return hit

        if state_c and state_c in STATES:
            lat, lon = STATES[state_c]
            return GeoResult("APPROXIMATE", lat, lon, "STATE", "GAZETTEER", state_c, state_c, "LOW",
                             "State centroid only – not shown on the map by default.")
        return GeoResult("UNRESOLVED", query=", ".join(x for x in (locality, city_c, state_c) if x) or None,
                         note="No city, locality or state could be resolved.")

    # ------------------------------------------------------------------ nominatim
    def _nominatim(self, query: str) -> GeoResult | None:
        key = f"nominatim|{query.lower()}"[:300]
        cached = self.db.get(GeocodeCache, key)
        if cached is not None:
            if cached.status == "OK":
                return GeoResult("APPROXIMATE", cached.latitude, cached.longitude, cached.precision, "NOMINATIM",
                                 query, cached.display_name, "MEDIUM")
            if cached.status == "NOT_FOUND":
                return GeoResult("UNRESOLVED", query=query, note="Not found (cached)")
            # ERROR entries are retried after one hour
            if (utcnow() - cached.created_at).total_seconds() < 3600:
                return None
        result, status = None, "NOT_FOUND"
        try:
            data = self._request(query)
            for item in data:
                lat, lon = float(item["lat"]), float(item["lon"])
                if valid_india_coords(lat, lon):
                    result = GeoResult("APPROXIMATE", lat, lon, None, "NOMINATIM", query, item.get("display_name"), "MEDIUM")
                    status = "OK"
                    break
        except Exception as e:  # network / HTTP / parse errors are not fatal
            log.warning("Nominatim lookup failed for %r: %s", query, e)
            status = "ERROR"
        # Cache writes use their own short transaction so the caller's session never holds
        # the database write lock across subsequent network calls.
        with SessionLocal() as cache_db:
            row = cache_db.get(GeocodeCache, key) or GeocodeCache(key=key)
            row.provider, row.status, row.created_at = "nominatim", status, utcnow()
            row.latitude = result.latitude if result else None
            row.longitude = result.longitude if result else None
            row.display_name = result.display_name if result else None
            cache_db.merge(row)
            cache_db.commit()
        if cached is not None:
            self.db.expire(cached)
        if status == "ERROR":
            return None
        return result or GeoResult("UNRESOLVED", query=query, note="Not found")

    def _request(self, query: str) -> list:
        ua = "AviralRoadDisruptionIntel/1.0"
        if settings.nominatim_contact:
            ua += f" ({settings.nominatim_contact})"
        params = {"q": query, "format": "jsonv2", "limit": 3, "countrycodes": "in", "addressdetails": 0}
        with _nominatim_lock:
            wait = MIN_INTERVAL - (time.monotonic() - _last_call[0])
            if wait > 0:
                time.sleep(wait)
            try:
                client = self.client or httpx.Client(timeout=10)
                try:
                    resp = client.get(f"{settings.nominatim_url.rstrip('/')}/search", params=params,
                                      headers={"User-Agent": ua, "Accept-Language": "en"})
                finally:
                    if self.client is None:
                        client.close()
            finally:
                _last_call[0] = time.monotonic()
        if resp.status_code == 429:
            raise RuntimeError("Nominatim rate limit (HTTP 429)")
        resp.raise_for_status()
        data = resp.json()
        if not isinstance(data, list):
            raise ValueError("Unexpected Nominatim response")
        return data
