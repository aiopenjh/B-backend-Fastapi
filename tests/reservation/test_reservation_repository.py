import uuid
from datetime import datetime, UTC

from reservation.domain.reservation import Reservation, ReservationStatus
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
    
    expected = Reservation(
        id=13, 
        user_id=uuid.UUID("00000000-0000-4000-8000-000000000001"),
        slot_id=7, 
        party_size=2, 
        contact_phone="010-0000-0000", 
        status=ReservationStatus.CANCELLED,
        created_at=CREATE_AT_NOW,
        cancelled_at=CANCELLED_AT_NOW
        )

    reservation = to_reservation(model)

    assert reservation == expected
    assert reservation.status is ReservationStatus.CANCELLED