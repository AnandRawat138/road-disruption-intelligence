from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import osmnx as ox
import json

from app.models.road import Road

engine = create_engine('sqlite:///./roaddb.db')
Session = sessionmaker(bind=engine)
db = Session()

roads = db.query(Road).all()
for r in roads:
    if not r.latitude or not r.longitude:
        continue
    try:
        custom_filter = '["highway"~"motorway|trunk|primary|secondary"]'
        G = ox.graph_from_point((r.latitude, r.longitude), dist=1000, network_type='drive', custom_filter=custom_filter)
        nearest_edge = ox.distance.nearest_edges(G, X=r.longitude, Y=r.latitude)
        if nearest_edge:
            u, v, key = nearest_edge
            edge_data = G.get_edge_data(u, v, key)
            if 'geometry' in edge_data:
                coords = list(edge_data['geometry'].coords)
            else:
                coords = [[G.nodes[u]['x'], G.nodes[u]['y']], [G.nodes[v]['x'], G.nodes[v]['y']]]
            
            r.geometry_json = json.dumps({'type': 'LineString', 'coordinates': coords})
            print(f'Updated geometry for {r.name}')
    except Exception as e:
        print(f'Skipped {r.name}: {e}')

db.commit()
