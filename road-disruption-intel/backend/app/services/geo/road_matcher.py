import osmnx as ox
from typing import List
from app.models.road import Road
from app.services.geo.geocoder import GeoLocation
import uuid

class RoadMatcher:
    def __init__(self):
        ox.settings.log_console = False
        ox.settings.use_cache = True
        
    def match_roads(self, event_locations: List[GeoLocation], radius: int = 500) -> List[Road]:
        matched_roads = []
        for loc in event_locations:
            if loc.status != "RESOLVED":
                continue
                
            try:
                custom_filter = '["highway"~"motorway|trunk|primary|secondary"]'
                G = ox.graph_from_point((loc.latitude, loc.longitude), dist=radius, network_type='drive', custom_filter=custom_filter)
                
                nearest_edge = ox.distance.nearest_edges(G, X=loc.longitude, Y=loc.latitude)
                if nearest_edge:
                    u, v, key = nearest_edge
                    edge_data = G.get_edge_data(u, v, key)
                    
                    name = edge_data.get('name', 'Unknown Road')
                    if isinstance(name, list):
                        name = name[0]
                        
                    highway_type = edge_data.get('highway', 'unknown')
                    if isinstance(highway_type, list):
                        highway_type = highway_type[0]
                    
                    # Extract Highway Number if present (e.g. "NH-19" or "ref")
                    ref = edge_data.get('ref', '')
                    if isinstance(ref, list):
                        ref = ref[0]
                        
                    # Calculate Match Confidence and Type
                    # If the location text contained the highway ref or name, it's DIRECT
                    orig_text = loc.original_text.lower()
                    
                    match_type = "NEARBY"
                    confidence = 0.6
                    
                    if name.lower() in orig_text:
                        match_type = "DIRECT"
                        confidence = 0.95
                    elif ref and ref.lower() in orig_text:
                        match_type = "HIGHWAY_ASSOCIATED"
                        confidence = 0.9
                    elif loc.location_type == "LANDMARK":
                        match_type = "LANDMARK_ASSOCIATED"
                        confidence = 0.7
                        
                    import json
                    if 'geometry' in edge_data:
                        coords = list(edge_data['geometry'].coords)
                    else:
                        coords = [[G.nodes[u]['x'], G.nodes[u]['y']], [G.nodes[v]['x'], G.nodes[v]['y']]]
                        
                    geom_json = json.dumps({
                        "type": "LineString",
                        "coordinates": coords
                    })
                    
                    matched_roads.append(Road(
                        osm_id=str(edge_data.get('osmid', '')),
                        name=name,
                        highway_number=ref if ref else None,
                        highway_type=highway_type,
                        city=loc.city,
                        state=loc.state,
                        latitude=loc.latitude,
                        longitude=loc.longitude,
                        matching_confidence=confidence,
                        geometry_json=geom_json
                    ))
            except Exception as e:
                print(f"Error matching road for location {loc.original_text}: {e}")
                
        return matched_roads
