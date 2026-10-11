from sqlalchemy.orm import Session
from app.models.event import Event
from app.models.evidence import Evidence
from app.models.article import Article
from app.services.evidence.confidence import ConfidenceScorer
from app.services.evidence.contradiction import ContradictionDetector
from datetime import datetime

class EvidenceFusionService:
    def __init__(self):
        self.scorer = ConfidenceScorer()
        self.detector = ContradictionDetector()

    def fuse_event(self, db: Session, new_event: Event, article: Article, evidence_text: str) -> Event:
        """
        Attempts to merge a newly extracted event with an existing active/upcoming event.
        If it matches, it adds Evidence instead of creating a duplicate.
        """
        # Find potential matches: Same city, active/upcoming
        candidates = db.query(Event).filter(
            Event.city == new_event.city,
            Event.status.in_(["UPCOMING", "ACTIVE"])
        ).all()
        
        matched_event = None
        for candidate in candidates:
            # Simple heuristic matching:
            # 1. Same event type
            # 2. Overlapping extracted roads
            common_roads = set(new_event.extracted_roads).intersection(set(candidate.extracted_roads))
            
            if candidate.event_type == new_event.event_type and (common_roads or new_event.extracted_roads == candidate.extracted_roads):
                matched_event = candidate
                break
                
        if not matched_event:
            # It's a truly new event
            db.add(new_event)
            db.flush() # get ID
            matched_event = new_event
        else:
            # We found a match, check for contradictions
            is_conflict, conflict_reason = self.detector.check_temporal_conflict(
                matched_event, new_event.start_time, new_event.end_time
            )
            # If no conflict, we might want to update the end time to the latest one, etc.
            if new_event.end_time and (not matched_event.end_time or new_event.end_time > matched_event.end_time):
                matched_event.end_time = new_event.end_time

        # Create Evidence linking this article to the event
        reliability = self.scorer.get_source_reliability(article.source_name)
        
        # Calculate semantic and temporal agreement grades
        t_agreement = 0.1 if (locals().get('is_conflict', False)) else 1.0
        
        # Check source independence (are we just fusing another syndicated article from the same source?)
        duplicate_source = db.query(Evidence).filter(
            Evidence.event_id == matched_event.id, 
            Evidence.source_name == article.source_name
        ).first()
        
        support = 0.5 if duplicate_source else 1.0 # discount duplicate source reports
        
        evidence = Evidence(
            event_id=matched_event.id,
            article_id=article.id,
            source_name=article.source_name,
            source_type="NEWS",
            source_reliability=reliability,
            evidence_text=evidence_text,
            support_score=support,
            contradiction_score=0.9 if t_agreement == 0.1 else 0.0,
            temporal_agreement=t_agreement,
            geographic_agreement=1.0 # Assumed high if fusion matched roads
        )
        db.add(evidence)
        db.flush()
        
        # Recalculate confidence
        all_evidence = db.query(Evidence).filter(Evidence.event_id == matched_event.id).all()
        new_confidence = self.scorer.calculate_event_confidence(matched_event, all_evidence)
        matched_event.certainty = new_confidence # updating the event's certainty/confidence score
        
        return matched_event
