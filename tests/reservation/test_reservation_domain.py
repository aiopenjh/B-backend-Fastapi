# 도메인 를래스의 업무 규칙이 맞게 동작하는지 테스트
from datetime import UTC, datetime

from reservation.domain.reservation import Reservation, ReservationStatus

NOW = datetime(2026, 11, 3, 6, 0, tzinfo=UTC)

def test_create_starts_confirmed():
    reservation = Reservation.create(user_id=1, slot_id=7, party_size=2, now=NOW)

    assert reservation.status is ReservationStatus.CONFIRMED
    assert reservation.created_at == NOW
    assert reservation.cancelled_at is None