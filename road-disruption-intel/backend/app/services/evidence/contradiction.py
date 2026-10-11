from datetime import datetime
from typing import Optional, Tuple
from app.models.event import Event

class ContradictionDetector:
    def check_temporal_conflict(self, existing_event: Event, new_start: Optional[datetime], new_end: Optional[datetime]) -> Tuple[bool, str]:
        """
        Detect if two reports for the same disruption have a severe temporal conflict.
        """
        if not existing_event.start_time or not new_start:
            return False, ""
            
        # If the new start time is completely outside the existing bounds (e.g. >2 days diff), flag it.
        delta = abs((existing_event.start_time - new_start).total_seconds())
        if delta > 48 * 3600: # 48 hours
            return True, "TEMPORAL: New report claims a start time >48h different from existing consensus."
            
        return False, ""
