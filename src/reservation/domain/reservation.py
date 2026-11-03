# Reservation을 만든다
from enum import StrEnum
from dataclasses import dataclass
from datetime import datetime

class ReservationStatus(StrEnum):
    CONFIRMED = "CONFIRMED"
    CANCELLED = "CANCELLED" 

@dataclass
class Reservation:
    user_id: int
    slot_id: int
    party_size: int
    contact_phone: str | None = None
    status: ReservationStatus
    created_at: datetime
    cancelled_at: datetime | None = None
    id: int | None = None