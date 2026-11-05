import uuid
from datetime import datetime, UTC

from reservation.domain.reservation import ReservationStatus
from reservation.infrastructure.models import ReservationModel
from reservation.infrastructure.repository import to_reservation

CREATE_AT_NOW = datetime(2026, 10, 3, 6, 0, tzinfo=UTC)
UPDATE_AT_NOW = datetime(2026, 11, 3, 6, 0, tzinfo=UTC)
CANCELLED_AT_NOW = datetime(2026, 12, 3, 6, 0, tzinfo=UTC)

def test_to_reservation_keeps_fields():
    model = ReservationModel(
        id=13, 
        user_id=uuid.UUID("00000000-0000-4000-8000-000000000001"),
        slot_id=7, 
        party_size=2, 
        contact_phone="010-0000-0000", 
        status="CANCELLED", 
        created_at=CREATE_AT_NOW, 
        updated_at=UPDATE_AT_NOW, 
        cancelled_at=CANCELLED_AT_NOW
        )
    reservation = to_reservation(model)

    assert reservation.id == model.id
    assert reservation.user_id == model.user_id
    assert reservation.slot_id == model.slot_id
    assert reservation.party_size == model.party_size
    assert reservation.contact_phone == model.contact_phone
    assert reservation.status is ReservationStatus.CANCELLED
    assert reservation.created_at == model.created_at
    assert reservation.cancelled_at == model.cancelled_at

    # assert to_reservation(model) == 

