from sqlalchemy.orm import Session
from app.models.event import Event
from app.models.road import Road
from app.models.disruption import Disruption
from typing import List

class DisruptionModeler:
    def map_event_to_roads(self, db: Session, event: Event, matched_roads: List[Road]):
        """
        Creates or updates Disruption objects linking an Event to specific Roads.
        Also infers the specific freight impact based on the event type and severity.
        """
        for road in matched_roads:
            # Check if this exact road is already mapped to this event
            existing = db.query(Disruption).filter(
                Disruption.event_id == event.id,
                Disruption.road_id == road.id
            ).first()
            
            if not existing:
                # Ensure the road is saved in DB to get an ID
                db_road = db.query(Road).filter(Road.osm_id == road.osm_id).first()
                if not db_road:
                    db.add(road)
                    db.flush()
                    db_road = road
                    
                disruption = Disruption(
                    event_id=event.id,
                    road_id=db_road.id,
                    impact_type=event.impact_type,
                    severity=event.severity,
                    confidence=event.certainty,
                    start_time=event.start_time,
                    end_time=event.end_time,
                    status=event.status
                )
                db.add(disruption)
                
    def get_freight_impact_text(self, impact_type: str, severity: float) -> str:
        """
        Generates SOW-compliant freight impact descriptions.
        """
        if impact_type == "FULL_CLOSURE":
            return "Through traffic suspended; Complete freight halt"
        elif impact_type == "TRAFFIC_DIVERSION" and severity > 0.7:
            return "Heavy vehicle diversion in effect"
        elif impact_type == "PARTIAL_CLOSURE":
            return "Intermittent blockage; Expect delays"
        else:
            return "Minor delays possible"
