import requests
import json
import math
from typing import List, Dict, Any
from sqlalchemy.orm import Session
from app.models.disruption import Disruption
from app.models.road import Road
from app.services.geo.geocoder import GeocoderService
from datetime import datetime
from sqlalchemy import or_, and_

class RoutingService:
    def __init__(self):
        self.geocoder = GeocoderService()
        self.osrm_base_url = "http://router.project-osrm.org/route/v1/driving"
        
    def _fetch_osrm_route(self, coords: List[tuple]) -> dict:
        coord_str = ";".join([f"{lon},{lat}" for lon, lat in coords])
        url = f"{self.osrm_base_url}/{coord_str}?overview=full&geometries=geojson"
        try:
            res = requests.get(url, timeout=10)
            data = res.json()
            if data.get("code") == "Ok" and len(data["routes"]) > 0:
                return data["routes"][0]["geometry"]
        except Exception as e:
            print(f"OSRM request failed: {e}")
        return None
        
    def _check_intersection(self, route_geom: dict, disruptions: List) -> tuple:
        """
        Simple bounding box collision to detect if a route hits an active disruption.
        Returns (is_intersected, disruption_center_lat, disruption_center_lon)
        """
        if not route_geom: return False, 0, 0
        coords = route_geom.get("coordinates", [])
        
        for idx, (lon, lat) in enumerate(coords):
            for d, road in disruptions:
                if not road.latitude or not road.longitude: continue
                # Simple ~2km radius check
                if abs(road.latitude - lat) < 0.02 and abs(road.longitude - lon) < 0.02:
                    return True, road.latitude, road.longitude
        return False, 0, 0

    def calculate_route(self, db: Session, origin: str, destination: str, departure_time: datetime = None) -> Dict[str, Any]:
        """
        Calculates a route from origin to destination using OSRM, checking for disruptions
        active at departure_time. If disrupted, computes an alternate bypass route.
        """
        if not departure_time:
            departure_time = datetime.utcnow()
            
        orig_geo = self.geocoder.resolve(origin)
        dest_geo = self.geocoder.resolve(destination)
        
        if orig_geo.status == "UNRESOLVED" or dest_geo.status == "UNRESOLVED":
            return {"error": "Could not geocode origin or destination"}
            
        # Fetch disruptions for the specific time slice G_t
        active_disruptions = db.query(Disruption, Road).join(Road).filter(
            or_(
                Disruption.status == "OPEN_ENDED",
                and_(
                    Disruption.start_time <= departure_time,
                    or_(Disruption.end_time == None, Disruption.end_time >= departure_time)
                )
            )
        ).all()
        
        # Get baseline route
        base_coords = [(orig_geo.longitude, orig_geo.latitude), (dest_geo.longitude, dest_geo.latitude)]
        normal_geometry = self._fetch_osrm_route(base_coords)
        
        if not normal_geometry:
            return {"error": "Routing engine could not find a path."}
            
        # Check for disruption interception
        is_affected, d_lat, d_lon = self._check_intersection(normal_geometry, active_disruptions)
        
        disruption_aware_geometry = None
        affected_roads_avoided = False
        
        if is_affected:
            # Generate a bypass route by forcing a detour waypoint 5km perpendicular to the disruption
            # (Crude but effective topological bypass for prototype)
            detour_lon = d_lon + 0.05
            detour_lat = d_lat - 0.05
            
            bypass_coords = [
                (orig_geo.longitude, orig_geo.latitude), 
                (detour_lon, detour_lat), 
                (dest_geo.longitude, dest_geo.latitude)
            ]
            disruption_aware_geometry = self._fetch_osrm_route(bypass_coords)
            affected_roads_avoided = True
        else:
            disruption_aware_geometry = normal_geometry
            
        return {
            "disruption_aware_route": [],
            "disruption_aware_geometry": disruption_aware_geometry,
            "normal_route": [],
            "normal_geometry": normal_geometry,
            "affected_roads_avoided": affected_roads_avoided
        }
