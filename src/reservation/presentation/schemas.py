# [담당 4] 예약 응답 모양 : API로 내보내는 예약 정보
import uuid
from datetime import datetime
from pydantic import BaseModel
from reservation.domain.reservation import ReservationStatus

class ReservationOut(BaseModel):
    id: int
    user_id: uuid.UUID
    slot_id: int
    restaurant_id: int
    starts_at: datetime
    ends_at: datetime
    party_size: int
    contact_phone: str | None
    status: ReservationStatus
    created_at: datetime
    cancelled_at: datetime | None
    can_cancel: bool