raise SystemExit("DISABLED: legacy v0 demo seed script. It deletes all records and inserts hand-written "
                 "events, which must never be presented as real intelligence. Kept only for reference.")

from app.db.database import SessionLocal
from app.models.event import Event
from app.models.road import Road
from app.models.disruption import Disruption
from app.models.article import Article
from app.models.evidence import Evidence
import json
import datetime

db = SessionLocal()

# Delete existing to showcase the 10 perfectly
db.query(Disruption).delete()
db.query(Evidence).delete()
db.query(Road).delete()
db.query(Event).delete()
db.query(Article).delete()
db.commit()

now = datetime.datetime.now()

events_data = [
    {
        "event_name": "New Delhi BRICS Leaders Summit Diversions",
        "description": "The Delhi Traffic Police issued a major public advisory ahead of the 18th BRICS Leaders' Summit. Extensive motorcade rehearsals regulated movement across 22 diversion points and affected over 35 central highways, including Sardar Patel Marg, Mathura Road, and Ashoka Road.",
        "event_type": "VIP_MOVEMENT", "impact_type": "TRAFFIC_DIVERSION",
        "city": "New Delhi", "state": "Delhi", "severity": 0.85, "certainty": 0.95,
        "road_name": "Mathura Road", "road_osm": "mathura_road", "lat": 28.6139, "lon": 77.2090,
        "source_name": "Times of India", "source_url": "https://timesofindia.indiatimes.com/city/delhi/ahead-of-brics-summit-2026-delhi-traffic-police-issues-advisory-for-commuters-check-key-routes/articleshow/133903671.cms",
        "start_time": datetime.datetime(2026, 9, 11, 0, 0), "end_time": datetime.datetime(2026, 9, 13, 23, 59)
    },
    {
        "event_name": "Lucknow-Kanpur Expressway Cave-In",
        "description": "Following intense monsoon downpours, severe structural caving was reported across multiple freshly constructed stretches of the Lucknow-Kanpur Expressway. The NHAI has suspended toll collections.",
        "event_type": "FLOODING", "impact_type": "FULL_CLOSURE",
        "city": "Kanpur", "state": "Uttar Pradesh", "severity": 0.90, "certainty": 1.0,
        "road_name": "Lucknow-Kanpur Expressway", "road_osm": "lko_knp_exp", "lat": 26.65, "lon": 80.6,
        "source_name": "NDTV", "source_url": "https://www.ndtv.com/topic/traffic",
        "start_time": datetime.datetime(2026, 9, 1, 0, 0), "end_time": None
    },
    {
        "event_name": "Kerala NH-66 Construction Zone Danger",
        "description": "Recurring accidents along under-construction stretches of NH-66. Keralam government directed NHAI to deploy emergency safety overrides, rectify traffic flows, and add lighting.",
        "event_type": "CONSTRUCTION", "impact_type": "POTENTIAL_BLOCKAGE",
        "city": "Thrissur", "state": "Kerala", "severity": 0.65, "certainty": 0.9,
        "road_name": "NH-66", "road_osm": "nh66_thrissur", "lat": 10.52, "lon": 76.21,
        "source_name": "The Hindu", "source_url": "https://www.thehindu.com/news/national/kerala/thrissur-road-accident-state-to-ensure-road-safety-amid-recurring-incidents-on-nh-says-keralam-minister/article71432393.ece",
        "start_time": datetime.datetime(2026, 9, 1, 0, 0), "end_time": None
    },
    {
        "event_name": "Itanagar VIP Visit Traffic Curfew",
        "description": "Traffic curbs across Itanagar on September 9 for the Vice President of India's visit. Severe No Parking Zones placed between JNK Traffic Point and Donyi Polo Hotel.",
        "event_type": "VIP_MOVEMENT", "impact_type": "TRAFFIC_DIVERSION",
        "city": "Itanagar", "state": "Arunachal Pradesh", "severity": 0.75, "certainty": 0.95,
        "road_name": "JNK Traffic Point Road", "road_osm": "jnk_itanagar", "lat": 27.08, "lon": 93.63,
        "source_name": "Arunachal News 365", "source_url": "https://www.facebook.com/arunachalnews365/videos/traffic-advisory-issued-in-itanagar-ahead-of-vice-presidents-visit-on-september-/1078493655001898/",
        "start_time": datetime.datetime(2026, 9, 9, 6, 0), "end_time": datetime.datetime(2026, 9, 9, 18, 0)
    },
    {
        "event_name": "Hyderabad Khajaguda Bottleneck",
        "description": "Commuting times doubled along Hyderabad IT corridor due to heavy construction on Khajaguda underpass and flyover constraining road spaces.",
        "event_type": "CONSTRUCTION", "impact_type": "HEAVY_TRAFFIC",
        "city": "Hyderabad", "state": "Telangana", "severity": 0.8, "certainty": 0.9,
        "road_name": "Khajaguda IT Corridor", "road_osm": "khajaguda_hyd", "lat": 17.41, "lon": 78.36,
        "source_name": "The Hindu", "source_url": "https://www.thehindu.com/topic/Roads_and_Rails/?item=",
        "start_time": datetime.datetime(2026, 8, 20, 0, 0), "end_time": None
    },
    {
        "event_name": "Suchitra-Kompally NH-44 Gridlock",
        "description": "Severe gridlocks for 1.5 lakh motorists navigating Hyderabad Suchitra-Kompally highway stretch (NH-44) due to stagnation of flyover project.",
        "event_type": "CONSTRUCTION", "impact_type": "HEAVY_TRAFFIC",
        "city": "Hyderabad", "state": "Telangana", "severity": 0.8, "certainty": 0.9,
        "road_name": "NH-44 Suchitra-Kompally", "road_osm": "nh44_hyd", "lat": 17.52, "lon": 78.47,
        "source_name": "The Hindu", "source_url": "https://www.thehindu.com/topic/Roads_and_Rails/?item=",
        "start_time": datetime.datetime(2026, 8, 15, 0, 0), "end_time": None
    }
]

for i, ed in enumerate(events_data):
    e = Event(
        event_type=ed["event_type"], impact_type=ed["impact_type"],
        event_name=ed["event_name"], description=ed["description"],
        city=ed["city"], state=ed["state"],
        severity=ed["severity"], certainty=ed["certainty"],
        start_time=ed["start_time"], end_time=ed["end_time"], status='ACTIVE'
    )
    db.add(e)
    db.flush()

    a = Article(
        title=ed["event_name"], source_name=ed["source_name"],
        source_url=ed["source_url"] + str(i), published_at=now, content_hash=f'hash_{i}'
    )
    db.add(a)
    db.flush()

    ev = Evidence(event_id=e.id, article_id=a.id, source_name=ed["source_name"], evidence_text=ed["description"])
    db.add(ev)

    lon, lat = ed["lon"], ed["lat"]
    r = Road(
        osm_id=ed["road_osm"], name=ed["road_name"], highway_type='trunk',
        city=ed["city"], state=ed["state"], latitude=lat, longitude=lon,
        geometry_json=json.dumps({'type': 'LineString', 'coordinates': [[lon-0.05, lat-0.05], [lon, lat], [lon+0.05, lat+0.05]]})
    )
    db.add(r)
    db.flush()

    d = Disruption(event_id=e.id, road_id=r.id, impact_type=ed["impact_type"], severity=ed["severity"], confidence=ed["certainty"], start_time=ed["start_time"], end_time=ed["end_time"], status='ACTIVE')
    db.add(d)

db.commit()
print('Seeded custom user articles!')
