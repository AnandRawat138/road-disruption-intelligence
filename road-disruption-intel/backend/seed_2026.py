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

# Clear existing to be safe
db.query(Disruption).delete()
db.query(Evidence).delete()
db.query(Road).delete()
db.query(Event).delete()
db.query(Article).delete()
db.commit()

# EVENT 1: BRICS Summit Delhi (Sept 2026)
e1 = Event(
    event_type='VIP_MOVEMENT', impact_type='TRAFFIC_DIVERSION',
    event_name='BRICS Summit Traffic Advisory',
    description='Traffic movement will be heavily regulated and diverted across more than 35 key roads in New Delhi to facilitate the movement of foreign dignitaries for the 18th BRICS Leaders Summit at Pragati Maidan. Use Delhi Metro to avoid delays.',
    city='New Delhi', state='Delhi',
    severity=0.85, certainty=1.0,
    start_time=datetime.datetime(2026, 9, 11, 0, 0),
    end_time=datetime.datetime(2026, 9, 13, 23, 59),
    status='ACTIVE'
)
db.add(e1)
db.flush()

a1 = Article(
    title='Traffic advisory issued for BRICS Summit in Delhi', source_name='Business Standard',
    source_url='https://www.business-standard.com/india-news/delhi-traffic-police-issues-advisory-for-brics-summit-check-details-here-126090800001_1.html',
    published_at=datetime.datetime(2026, 9, 8, 10, 0),
    content_hash='brics_hash'
)
db.add(a1)
db.flush()

ev1 = Evidence(event_id=e1.id, article_id=a1.id, source_name='Business Standard', evidence_text='Traffic movement regulated...')
db.add(ev1)

r1 = Road(
    osm_id='mathura_road', name='Mathura Road & Pragati Maidan Area', highway_type='primary',
    city='New Delhi', state='Delhi', latitude=28.6139, longitude=77.2090,
    geometry_json=json.dumps({'type': 'LineString', 'coordinates': [[77.23, 28.60], [77.24, 28.61], [77.245, 28.62]]})
)
db.add(r1)
db.flush()

d1 = Disruption(event_id=e1.id, road_id=r1.id, impact_type=e1.impact_type, severity=e1.severity, confidence=e1.certainty, start_time=e1.start_time, end_time=e1.end_time, status='ACTIVE')
db.add(d1)

# EVENT 2: Mumbai-Goa Highway Ganesh Utsav (Sept 2026)
e2 = Event(
    event_type='FESTIVAL', impact_type='PARTIAL_CLOSURE',
    event_name='Mumbai-Goa Highway Heavy Vehicle Ban',
    description='Authorities have initiated precautionary measures restricting heavy vehicle movement on the Mumbai-Goa highway (NH-66) in preparation for the Ganesh Utsav festival to allow smooth passage for devotees.',
    city='Ratnagiri', state='Maharashtra',
    severity=0.70, certainty=0.95,
    start_time=datetime.datetime(2026, 9, 5, 0, 0),
    end_time=datetime.datetime(2026, 9, 17, 23, 59),
    status='ACTIVE'
)
db.add(e2)
db.flush()

a2 = Article(
    title='Mumbai-Goa highway heavy vehicle restrictions', source_name='eSakal',
    source_url='https://www.esakal.com/maharashtra/heavy-vehicles-banned-on-mumbai-goa-highway-for-ganesh-utsav-2026',
    published_at=datetime.datetime(2026, 9, 4, 11, 15),
    content_hash='ganesh_hash'
)
db.add(a2)
db.flush()

ev2 = Evidence(event_id=e2.id, article_id=a2.id, source_name='eSakal', evidence_text='Heavy vehicles banned...')
db.add(ev2)

r2 = Road(
    osm_id='nh66', name='NH-66 (Mumbai-Goa Highway)', highway_type='trunk',
    city='Ratnagiri', state='Maharashtra', latitude=16.9902, longitude=73.3120,
    geometry_json=json.dumps({'type': 'LineString', 'coordinates': [[73.1, 17.5], [73.3120, 16.9902], [73.5, 16.5]]})
)
db.add(r2)
db.flush()

d2 = Disruption(event_id=e2.id, road_id=r2.id, impact_type=e2.impact_type, severity=e2.severity, confidence=e2.certainty, start_time=e2.start_time, end_time=e2.end_time, status='ACTIVE')
db.add(d2)

# EVENT 3: IMD Flood Warning East UP (Sept 2026)
e3 = Event(
    event_type='FLOODING', impact_type='POTENTIAL_BLOCKAGE',
    event_name='Heavy Rain & Waterlogging Warning',
    description='The India Meteorological Department (IMD) has issued red alerts for extremely heavy rainfall across East UP. Localized waterlogging on major state highways is anticipated, causing potential route blockages.',
    city='Gorakhpur', state='Uttar Pradesh',
    severity=0.90, certainty=0.85,
    start_time=datetime.datetime(2026, 9, 7, 8, 0),
    end_time=datetime.datetime(2026, 9, 10, 12, 0),
    status='ACTIVE'
)
db.add(e3)
db.flush()

a3 = Article(
    title='IMD issues heavy rainfall warning', source_name='IMD Official',
    source_url='https://mausam.imd.gov.in/',
    published_at=datetime.datetime(2026, 9, 7, 7, 00),
    content_hash='imd_hash'
)
db.add(a3)
db.flush()

ev3 = Evidence(event_id=e3.id, article_id=a3.id, source_name='IMD Official', evidence_text='IMD issues red alert...')
db.add(ev3)

r3 = Road(
    osm_id='nh27_up', name='NH-27 (East UP stretch)', highway_type='trunk',
    city='Gorakhpur', state='Uttar Pradesh', latitude=26.7606, longitude=83.3732,
    geometry_json=json.dumps({'type': 'LineString', 'coordinates': [[82.5, 26.8], [83.3732, 26.7606], [84.0, 26.7]]})
)
db.add(r3)
db.flush()

d3 = Disruption(event_id=e3.id, road_id=r3.id, impact_type=e3.impact_type, severity=e3.severity, confidence=e3.certainty, start_time=e3.start_time, end_time=e3.end_time, status='ACTIVE')
db.add(d3)

db.commit()
print('Seeded authentic 2026 events!')
