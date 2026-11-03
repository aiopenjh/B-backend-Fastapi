# Reservation을 만든다
from enum import StrEnum
from dataclasses import dataclass
from datetime import datetime
from typing import Self

class ReservationStatus(StrEnum):
    CONFIRMED = "CONFIRMED"
    CANCELLED = "CANCELLED" 

@dataclass
class Reservation:
    user_id: int
    slot_id: int
    party_size: int
    status: ReservationStatus
    created_at: datetime
    contact_phone: str | None = None
    cancelled_at: datetime | None = None
    id: int | None = None

    @classmethod
    def create(
        cls,
        user_id: int,
        slot_id: int,
        party_size: int,
        now: datetime,
        contact_phone: str | None = None,
    ) -> Self:
        return cls(
            user_id=user_id,
            slot_id=slot_id,
            party_size=party_size,
            status=ReservationStatus.CONFIRMED,
            created_at=now,
            contact_phone=contact_phone
        )
    
    def cancel(self, now: datetime, slot) -> None:
        self.status = ReservationStatus.CANCELLED
        self.cancelled_at = now