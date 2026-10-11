import dateparser
from datetime import datetime
from typing import Optional, Tuple

class TemporalNormalizer:
    def __init__(self):
        # We assume IST (Asia/Kolkata) for Indian context but return naive datetimes for SQLite compatibility
        self.settings = {'TIMEZONE': 'Asia/Kolkata', 'RETURN_AS_TIMEZONE_AWARE': False}

    def normalize(self, time_expression: str, reference_date: datetime) -> Optional[datetime]:
        """
        Convert a natural language time expression into a standard datetime object.
        Uses the publication date of the article as the reference point.
        """
        if not time_expression:
            return None
            
        settings = self.settings.copy()
        settings['RELATIVE_BASE'] = reference_date
        
        try:
            parsed_date = dateparser.parse(time_expression, settings=settings)
            return parsed_date
        except Exception as e:
            print(f"Failed to parse date '{time_expression}': {e}")
            return None

    def resolve_interval(self, temporal_expression: str, start_expr: str, end_expr: str, reference_date: datetime) -> Tuple[Optional[datetime], Optional[datetime], str, float]:
        """
        Resolve a start and end expression pair into a normalized interval.
        Returns: (start_time, end_time, status, temporal_confidence)
        """
        start_time = self.normalize(start_expr, reference_date) if start_expr else None
        end_time = self.normalize(end_expr, reference_date) if end_expr else None
        
        confidence = 1.0
        status = "UNCERTAIN"
        now = datetime.utcnow()
        
        # Analyze natural language expression for edge cases
        exp_lower = (temporal_expression or "").lower()
        
        if "until further notice" in exp_lower or "until" in exp_lower and not end_time:
            # Open-ended event
            end_time = None
            status = "OPEN_ENDED"
            confidence = 0.8
        
        # If we have start and end, ensure end is after start
        if start_time and end_time and end_time < start_time:
            # Shift end to the next day if it seems wrapped
            # (Very basic heuristic)
            pass 
            
        # Determine Status if not explicitly open-ended
        if status != "OPEN_ENDED":
            if start_time and end_time:
                if now < start_time:
                    status = "UPCOMING"
                elif start_time <= now <= end_time:
                    status = "ACTIVE"
                else:
                    status = "EXPIRED"
            elif start_time and not end_time:
                if now < start_time:
                    status = "UPCOMING"
                else:
                    status = "ACTIVE" # Missing end time, assumed active
                    confidence = 0.6
            elif not start_time and end_time:
                if now <= end_time:
                    status = "ACTIVE"
                    confidence = 0.6
                else:
                    status = "EXPIRED"
            else:
                status = "ACTIVE" # Default fallback for missing both
                confidence = 0.4
                
        return start_time, end_time, status, confidence
