from app.models.event import Event
from app.models.evidence import Evidence
from typing import List

class ConfidenceScorer:
    def __init__(self):
        # Base reliabilities based on SOW
        self.source_weights = {
            "official_traffic_authority": 1.0,
            "government": 0.95,
            "major_news": 0.85,
            "local_news": 0.75,
            "unknown_source": 0.50
        }

    def get_source_reliability(self, source_name: str) -> float:
        name = source_name.lower()
        if any(gov in name for gov in ["nhai", "morth", "police", "ndma", "sdma", "traffic", "government"]):
            return self.source_weights["government"]
        elif "news" in name or "times" in name or "express" in name or "hindu" in name:
            return self.source_weights["major_news"]
        return self.source_weights["unknown_source"]

    def calculate_event_confidence(self, event: Event, evidences: List[Evidence]) -> float:
        """
        Calculate overall confidence (0.0 to 1.0) based on multiple evidence sources.
        """
        if not evidences:
            return 0.0
            
        # 1. Base score is the highest reliability source
        max_reliability = max(e.source_reliability for e in evidences)
        
        # 2. Additive boost for multiple independent sources (diminishing returns)
        # using the support_score to discount duplicate sources
        independent_sources = sum(e.support_score for e in evidences)
        multi_source_boost = 0.0
        if independent_sources >= 1.5 and independent_sources < 2.5:
            multi_source_boost = 0.10
        elif independent_sources >= 2.5:
            multi_source_boost = 0.15
            
        # 3. Penalty for temporal/geographic disagreements and contradictions
        avg_temporal_agreement = sum(e.temporal_agreement for e in evidences) / len(evidences)
        avg_geo_agreement = sum(e.geographic_agreement for e in evidences) / len(evidences)
        max_contradiction = max((e.contradiction_score for e in evidences), default=0.0)
        
        disagreement_penalty = 0.0
        if avg_temporal_agreement < 0.5 or avg_geo_agreement < 0.5:
            disagreement_penalty += 0.15
        if max_contradiction > 0.5:
            disagreement_penalty += 0.20
            
        # 4. Extraction certainty (from LLM) and Temporal Reasoner confidence
        extraction_factor = event.certainty if event.certainty else 0.8
        temp_conf = event.temporal_confidence if event.temporal_confidence else 1.0
        
        raw_score = (max_reliability + multi_source_boost - disagreement_penalty) * (extraction_factor * 0.8 + temp_conf * 0.2)
        
        confidence = max(0.0, min(1.0, raw_score))
        
        # Also update Road Risk Score
        self._update_road_risk(event, confidence)
        
        return confidence
        
    def _update_road_risk(self, event: Event, confidence: float):
        # High severity + High confidence = Critical Risk
        # High severity + Low confidence = Medium Risk
        severity = event.severity if event.severity else 0.5
        
        # Temporal proximity (ACTIVE = highest risk)
        temp_mult = 1.0
        if event.status == "EXPIRED":
            temp_mult = 0.1
        elif event.status == "UPCOMING":
            temp_mult = 0.7
            
        event.road_risk_score = max(0.0, min(1.0, severity * confidence * temp_mult))
