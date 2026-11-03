from dataclasses import dataclass
from datetime import datetime

from slot.domain.exceptions import (
    SlotAlreadyStarted,
    PartySizeExceeded,
    SlotSoldOut,    
    SlotRuleViolation,
)

@dataclass
class TimeSlot:
    id: int 
    restaurant_id: int
    starts_at: datetime
    ends_at: datetime
    capacity: int
    reserved_guests: int
    max_party_size: int
