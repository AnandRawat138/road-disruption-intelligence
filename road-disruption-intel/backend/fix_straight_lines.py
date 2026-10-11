from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import requests
import json

from app.models.road import Road

engine = create_engine('sqlite:///./roaddb.db')
Session = sessionmaker(bind=engine)
db = Session()

def get_osrm_curve(lat, lon):
    url = f"http://router.project-osrm.org/route/v1/driving/{lon-0.02},{lat-0.02};{lon+0.02},{lat+0.02}?overview=full&geometries=geojson"
    try:
        res = requests.get(url, timeout=5)
        data = res.json()
        if data.get("code") == "Ok" and len(data["routes"]) > 0:
            return data["routes"][0]["geometry"]
    except Exception as e:
        print(f"OSRM error: {e}")
    return None

roads = db.query(Road).all()
for r in roads:
    if not r.latitude or not r.longitude:
        continue
    
    # Just force update everything that doesn't have a lot of coords
    needs_update = False
    if r.geometry_json:
        try:
            geom = json.loads(r.geometry_json)
            if geom.get("type") == "LineString" and len(geom.get("coordinates", [])) <= 5:
                needs_update = True
        except:
            needs_update = True
    else:
        needs_update = True
        
    if needs_update:
        print(f"Fixing geometry for {r.name}...")
        curved_geom = get_osrm_curve(r.latitude, r.longitude)
        if curved_geom:
            r.geometry_json = json.dumps(curved_geom)
            print(f" -> Success! Attached realistic curved road segment.")
        else:
            print(f" -> Failed to get OSRM route.")

db.commit()
print("Database updated!")
