# [담당 4] 예약 도메인 : 예약 상태와 취소 규칙
import uuid
from enum import StrEnum
from dataclasses import dataclass
from datetime import datetime
from typing import Self

from reservation.domain.exceptions import AlreadyCancelledError

class ReservationStatus(StrEnum):
    CONFIRMED = "CONFIRMED"
    CANCELLED = "CANCELLED" 

@dataclass
class Reservation:
    user_id: uuid.UUID
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
        user_id: uuid.UUID,
        slot_id: int,
        party_size: int,
        now: datetime,
        contact_phone: str | None = None,
    ) -> Self:
        # 새 예약은 항상 확정(CONFIRMED)으로 시작한다.
        return cls(
            user_id=user_id,
            slot_id=slot_id,
            party_size=party_size,
            status=ReservationStatus.CONFIRMED,
            created_at=now,
            contact_phone=contact_phone
        )
    
    def cancel(self, now: datetime, slot) -> None:
        if self.status is ReservationStatus.CANCELLED:
            raise AlreadyCancelledError()
        self.status = ReservationStatus.CANCELLED
        self.cancelled_at = now
