from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut, GeocoderUnavailable
from pydantic import BaseModel
from typing import Optional
from app.config import settings

class GeoLocation(BaseModel):
    name: str
    original_text: str
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    city: str
    state: str
    confidence: float
    location_type: str = "UNKNOWN"
    status: str # RESOLVED, UNRESOLVED

class GeocoderService:
    def __init__(self):
        # Always include India in the context for accurate localization
        self.default_country = "India"
        self.geolocator = Nominatim(user_agent="road_disruption_intel")

    def resolve(self, location_text: str, city_context: Optional[str] = None, state_context: Optional[str] = None) -> GeoLocation:
        """
        Geocodes a text location into latitude and longitude, appending city/state context to improve accuracy.
        """
        if not location_text:
            return self._unresolved(location_text)
            
        # Build search query string
        query_parts = [location_text]
        if city_context:
            query_parts.append(city_context)
        if state_context:
            query_parts.append(state_context)
        query_parts.append(self.default_country)
        
        search_query = ", ".join(query_parts)
        
        try:
            location = self.geolocator.geocode(search_query, timeout=10)
            if location:
                # Basic heuristic for location type
                loc_type = "ROAD" if any(x in location_text.lower() for x in ["road", "marg", "highway", "nh-"]) else "LANDMARK"
                
                return GeoLocation(
                    name=location.address,
                    original_text=location_text,
                    latitude=location.latitude,
                    longitude=location.longitude,
                    city=city_context or "",
                    state=state_context or "",
                    confidence=0.8,
                    location_type=loc_type,
                    status="RESOLVED"
                )
        except (GeocoderTimedOut, GeocoderUnavailable) as e:
            print(f"Geocoding service unavailable or timed out: {e}")
            
        return self._unresolved(location_text)

    def _unresolved(self, name: str) -> GeoLocation:
        return GeoLocation(
            name=name,
            original_text=name,
            latitude=None,
            longitude=None,
            city="",
            state="",
            confidence=0.0,
            location_type="UNKNOWN",
            status="UNRESOLVED"
        )
