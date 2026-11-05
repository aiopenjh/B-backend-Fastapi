# [담당 4] 예약 도메인 규칙 테스트 : 생성과 취소
import uuid
import pytest
from datetime import UTC, datetime

from reservation.domain.reservation import Reservation, ReservationStatus
from reservation.domain.exceptions import AlreadyCancelledError

NOW = datetime(2026, 11, 3, 6, 0, tzinfo=UTC)
USER_ID = uuid.UUID("00000000-0000-4000-8000-000000000001")
OTHER_USER_ID = uuid.UUID("00000000-0000-4000-8000-000000000002")

def test_create_starts_confirmed():
    reservation = Reservation.create(user_id=USER_ID, slot_id=7, party_size=2, now=NOW)

    # 새 예약은 확정 상태이고, 취소 시각은 비어 있다.
    assert reservation.status is ReservationStatus.CONFIRMED
    assert reservation.created_at == NOW
    assert reservation.cancelled_at is None

def test_cancel_marks_cancelled_with_time():
    reservation = Reservation.create(user_id=USER_ID, slot_id=7, party_size=2, now=NOW)

    reservation.cancel(now=NOW)

    # 취소하면 상태가 바뀌고 취소 시각이 남는다.
    assert reservation.status is ReservationStatus.CANCELLED
    assert reservation.cancelled_at == NOW 

def test_cancel_twice_raises_already_cancelled():
    reservation = Reservation.create(user_id=USER_ID, slot_id=7, party_size=2, now=NOW)

    # 이미 취소된 상태를 만든다.
    reservation.cancel(now=NOW)

    # 한 번 더 취소하면 에러가 나야 한다.
    with pytest.raises(AlreadyCancelledError):
        reservation.cancel(now=NOW)

def test_can_cancel_true_for_owner_confirmed():
    reservation = Reservation.create(user_id=USER_ID, slot_id=7, party_size=2, now=NOW)

    # 예약한 본인이 요청하면 취소할 수 있어야 한다.
    assert reservation.can_cancel(user_id=USER_ID) is True

def test_can_cancel_false_for_other_user():
    reservation = Reservation.create(user_id=OTHER_USER_ID, slot_id=7, party_size=2, now=NOW)

    # 다른 사람이 요청하면 취소할 수 없어야 한다.
    assert reservation.can_cancel(user_id=USER_ID) is False

def test_can_cancel_false_when_already_cancelled():
    reservation = Reservation.create(user_id=USER_ID, slot_id=7, party_size=2, now=NOW)

    reservation.cancel(now=NOW)

    # 취소된 예약은 본인이어도 취소할 수 없어야 한다.
    assert reservation.can_cancel(user_id=USER_ID) is False
