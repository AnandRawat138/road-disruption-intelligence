from app.db.database import SessionLocal
from app.models.article import Article
from app.models.event import Event
from datetime import datetime
from app.services.nlp.relevance import RelevanceDetector
from app.services.nlp.extraction import EventExtractor
from app.services.nlp.temporal import TemporalNormalizer
from app.services.geo.geocoder import GeocoderService
from app.services.geo.road_matcher import RoadMatcher
from app.services.evidence.fusion import EvidenceFusionService
from app.services.routing.disruption_model import DisruptionModeler

def run_processing():
    print("Starting article NLP & Geo processing pipeline...")
    db = SessionLocal()
    detector = RelevanceDetector()
    extractor = EventExtractor()
    temporal = TemporalNormalizer()
    geocoder = GeocoderService()
    road_matcher = RoadMatcher()
    fusion_service = EvidenceFusionService()
    disruption_modeler = DisruptionModeler()
    
    try:
        pending_articles = db.query(Article).filter(Article.status == "PENDING").limit(10).all()
        processed_count = 0
        
        for article in pending_articles:
            rel_result = detector.assess(article.title, article.content)
            article.relevance_score = rel_result.score
            article.relevance_reason = rel_result.reason
            
            if rel_result.status in ["RELEVANT", "POSSIBLY_RELEVANT"]:
                extracted_data = extractor.extract(article.title, article.content, str(article.id))
                
                if extracted_data:
                    ref_date = article.published_at or article.collected_at
                    
                    # New Temporal Reasoner returning explicit confidence
                    start_time, end_time, temp_status, temp_conf = temporal.resolve_interval(
                        extracted_data.temporal_expression,
                        str(extracted_data.start_time) if extracted_data.start_time else "",
                        str(extracted_data.end_time) if extracted_data.end_time else "",
                        ref_date
                    )
                    
                    resolved_locations = []
                    for loc_str in extracted_data.roads + extracted_data.locations:
                        resolved = geocoder.resolve(loc_str, city_context=extracted_data.city, state_context=extracted_data.state)
                        resolved_locations.append(resolved)
                        
                    matched_roads = road_matcher.match_roads(resolved_locations)
                    
                    new_event = Event(
                        event_type=extracted_data.event_type,
                        impact_type=extracted_data.impact_type,
                        event_name=extracted_data.event_name,
                        description=extracted_data.description,
                        city=extracted_data.city,
                        state=extracted_data.state,
                        
                        # Temporal 
                        original_temporal_expression=extracted_data.temporal_expression,
                        start_time=start_time or extracted_data.start_time,
                        end_time=end_time or extracted_data.end_time,
                        temporal_confidence=temp_conf,
                        status=temp_status, # UPCOMING, ACTIVE, EXPIRED, OPEN_ENDED
                        
                        severity=extracted_data.severity,
                        certainty=extracted_data.extraction_confidence,
                        extracted_locations=[l.dict() for l in resolved_locations],
                        extracted_roads=[r.name for r in matched_roads]
                    )
                    
                    
                    evidence_text = " ".join(extracted_data.evidence_text)
                    matched_event = fusion_service.fuse_event(db, new_event, article, evidence_text)
                    
                    disruption_modeler.map_event_to_roads(db, matched_event, matched_roads)
                    
                    # --- NEW: Export to ML Dataset ---
                    if matched_event.certainty >= 0.7:
                        import json
                        import os
                        dataset_path = os.path.join(os.path.dirname(__file__), '../../ml_dataset.jsonl')
                        ml_record = {
                            "dataset_version": "2.0-research",
                            "timestamp": datetime.utcnow().isoformat(),
                            "source_text": article.content or article.description,
                            "source_title": article.title,
                            "extraction_labels": {
                                "event_type": matched_event.event_type,
                                "impact_type": matched_event.impact_type,
                                "severity": matched_event.severity,
                                "certainty": matched_event.certainty,
                                "temporal_expression_raw": matched_event.original_temporal_expression,
                                "temporal_confidence": matched_event.temporal_confidence,
                                "road_risk_score": matched_event.road_risk_score,
                                "locations_geocoded": [loc.dict() for loc in resolved_locations],
                                "matched_roads": [
                                    {
                                        "name": r.name,
                                        "osm_id": r.osm_id,
                                        "confidence": r.matching_confidence
                                    } for r in matched_roads
                                ]
                            }
                        }
                        with open(dataset_path, 'a', encoding='utf-8') as f:
                            f.write(json.dumps(ml_record) + "\n")
                    # ---------------------------------
                    
            article.status = "PROCESSED"
            processed_count += 1
            db.commit()  # <-- Commit immediately after each article so the UI updates instantly!
            print(f"Successfully processed and committed article {processed_count}: {article.title}")
            
        print(f"Finished processing batch of {processed_count} articles.")
    except Exception as e:
        db.rollback()
        print(f"Processing error: {e}")
    finally:
        db.close()
