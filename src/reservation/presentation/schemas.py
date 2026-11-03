# ReservationOut 을 만든다.
from datetime import datetime
from pydantic import BaseModel
from reservation.domain.reservation import ReservationStatus

class ReservationOut(BaseModel):
    id: int
    user_id: int
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