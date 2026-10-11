from pydantic import BaseModel
import re

class RelevanceResult(BaseModel):
    score: float
    reason: str
    status: str # RELEVANT, POSSIBLY_RELEVANT, IRRELEVANT

class RelevanceDetector:
    def __init__(self):
        # High confidence disruption keywords
        self.strong_keywords = [
            "road closure", "traffic diversion", "road blocked", "highway blocked",
            "traffic restricted", "heavy traffic jam", "route diverted", "bridge collapsed",
            "nh closed", "highway closed", "transport strike", "chakka jam"
        ]
        
        # Medium confidence keywords
        self.weak_keywords = [
            "procession", "accident", "waterlogging", "landslide",
            "protest", "rally", "vip movement", "construction"
        ]

    def assess(self, title: str, content: str) -> RelevanceResult:
        text = f"{title} {content}".lower()
        
        strong_matches = sum(1 for kw in self.strong_keywords if kw in text)
        weak_matches = sum(1 for kw in self.weak_keywords if kw in text)
        
        if strong_matches > 0:
            return RelevanceResult(
                score=0.9,
                reason=f"Found {strong_matches} strong disruption indicators.",
                status="RELEVANT"
            )
        elif weak_matches > 1:
            return RelevanceResult(
                score=0.6,
                reason=f"Found {weak_matches} potential disruption events, needs LLM verification.",
                status="POSSIBLY_RELEVANT"
            )
        elif weak_matches == 1:
            return RelevanceResult(
                score=0.3,
                reason="Minor mention of a disruption event.",
                status="IRRELEVANT"
            )
        else:
            return RelevanceResult(
                score=0.0,
                reason="No road disruption keywords detected.",
                status="IRRELEVANT"
            )
