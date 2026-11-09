# [담당 4] 예약 응답 스키마 테스트 : API 명세 예시, from_domain 변환, can_cancel 값
import uuid
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from common.schemas import SEOUL
from reservation.domain.reservation import Reservation, ReservationStatus
from reservation.presentation.schemas import ReservationCreate, ReservationOut
from slot.domain.time_slot import TimeSlot

# API 명세서의 응답 예시 그대로
SPEC_EXAMPLE = {
    "id": 15,
    "user_id": "00000000-0000-4000-8000-000000000001",
    "slot_id": 7,
    "restaurant_id": 1,
    "starts_at": "2026-10-30T18:00:00+09:00",
    "ends_at": "2026-10-30T19:00:00+09:00",
    "party_size": 2,
    "contact_phone": "010-1234-5678",
    "status": "CONFIRMED",
    "created_at": "2026-10-28T15:20:00+09:00",
    "cancelled_at": None,
    "can_cancel": True,
}

OWNER_ID = uuid.UUID("00000000-0000-4000-8000-000000000001")
GUEST_ID = uuid.UUID("00000000-0000-4000-8000-000000000002")
CREATED_AT = datetime(2026, 12, 1, 15, 0, tzinfo=SEOUL)
NOW = datetime(2026, 12, 3, 17, 0, tzinfo=SEOUL)
STARTS_AT = datetime(2026, 12, 3, 18, 0, tzinfo=SEOUL)
ENDS_AT = datetime(2026, 12, 3, 19, 0, tzinfo=SEOUL)

TIME_SLOT_EXAMPLE = {
    "id": 7,
    "restaurant_id": 1,
    "starts_at": STARTS_AT,
    "ends_at": ENDS_AT,
    "capacity": 10,
    "reserved_guests": 2,
    "max_party_size": 4,
}


# 명세 예시를 그대로 받아들이는지
def test_reservation_out_accepts_spec_example():
    reservation = ReservationOut(**SPEC_EXAMPLE)

    assert reservation.id == 15
    assert reservation.status == "CONFIRMED"
    assert reservation.cancelled_at is None


# 예약 + 슬롯을 합쳐 응답칸들이 모두 맞게 채워지는지
def test_from_domain_combines_reservation_and_slot():
    slot = TimeSlot(**TIME_SLOT_EXAMPLE)
    reservation = Reservation(
        id=3,
        user_id=OWNER_ID,
        slot_id=7,
        party_size=2,
        contact_phone="010-1234-5678",
        status=ReservationStatus.CONFIRMED,
        created_at=CREATED_AT,
        cancelled_at=None,
    )
    expected = ReservationOut(
        id=3,
        user_id=OWNER_ID,
        slot_id=7,
        restaurant_id=1,
        starts_at=STARTS_AT,
        ends_at=ENDS_AT,
        party_size=2,
        contact_phone="010-1234-5678",
        status=ReservationStatus.CONFIRMED,
        created_at=CREATED_AT,
        cancelled_at=None,
        can_cancel=True,
    )

    out = ReservationOut.from_domain(reservation, slot, OWNER_ID, NOW)

    assert out == expected


# 다른 사람이 보면 can_cancel은 False
def test_from_domain_can_cancel_false_for_other_viewer():
    slot = TimeSlot(**TIME_SLOT_EXAMPLE)
    reservation = Reservation(
        id=3,
        user_id=OWNER_ID,
        slot_id=7,
        party_size=2,
        contact_phone="010-1234-5678",
        status=ReservationStatus.CONFIRMED,
        created_at=CREATED_AT,
        cancelled_at=None,
    )
    out = ReservationOut.from_domain(reservation, slot, GUEST_ID, NOW)

    assert out.can_cancel is False


# 이미 취소된 예약은 본인이 봐도 can_cancel은 False
def test_from_domain_can_cancel_false_when_cancelled():
    slot = TimeSlot(**TIME_SLOT_EXAMPLE)
    reservation = Reservation(
        id=3,
        user_id=OWNER_ID,
        slot_id=7,
        party_size=2,
        contact_phone="010-1234-5678",
        status=ReservationStatus.CANCELLED,
        created_at=CREATED_AT,
        cancelled_at=NOW,
    )

    out = ReservationOut.from_domain(reservation, slot, OWNER_ID, NOW)

    assert out.can_cancel is False


# 슬롯이 시작된 순간(경계값)부터는 본인이 봐도 can_cancel은 False
def test_from_domain_can_cancel_false_after_slot_started():
    slot = TimeSlot(**TIME_SLOT_EXAMPLE)
    reservation = Reservation(
        id=3,
        user_id=OWNER_ID,
        slot_id=7,
        party_size=2,
        contact_phone="010-1234-5678",
        status=ReservationStatus.CONFIRMED,
        created_at=CREATED_AT,
        cancelled_at=None,
    )

    out = ReservationOut.from_domain(reservation, slot, OWNER_ID, STARTS_AT)

    assert out.can_cancel is False


# DB에서 꺼낸 시각(UTC)을 응답에서는 서울 시간(+09:00)으로 바꿔 내보내는지
def test_from_domain_converts_times_to_seoul():
    slot = TimeSlot(
        **{
            **TIME_SLOT_EXAMPLE,
            "starts_at": STARTS_AT.astimezone(UTC),
            "ends_at": ENDS_AT.astimezone(UTC),
        }
    )
    reservation = Reservation(
        id=3,
        user_id=OWNER_ID,
        slot_id=7,
        party_size=2,
        status=ReservationStatus.CANCELLED,
        created_at=CREATED_AT.astimezone(UTC),
        cancelled_at=NOW.astimezone(UTC),
    )

    body = ReservationOut.from_domain(reservation, slot, OWNER_ID, NOW).model_dump(
        mode="json"
    )

    assert body["starts_at"] == "2026-12-03T18:00:00+09:00"
    assert body["ends_at"] == "2026-12-03T19:00:00+09:00"
    assert body["created_at"] == "2026-12-01T15:00:00+09:00"
    assert body["cancelled_at"] == "2026-12-03T17:00:00+09:00"


# 명세의 요청 예시를 그대로 받아들이는지
def test_reservation_create_accepts_spec_example():
    body = ReservationCreate(slot_id=7, party_size=2, contact_phone="010-1234-5678")

    assert body.slot_id == 7
    assert body.party_size == 2
    assert body.contact_phone == "010-1234-5678"


# 연락처는 안 보내도 된다 (선택)
def test_reservation_create_contact_phone_is_optional():
    body = ReservationCreate(slot_id=7, party_size=2)

    assert body.contact_phone is None


# 인원이 0명 이하면 막는다
def test_reservation_create_rejects_zero_party_size():
    with pytest.raises(ValidationError):
        ReservationCreate(slot_id=7, party_size=0)


# 연락처 앞뒤 공백은 지우고 받는다
def test_reservation_create_strips_contact_phone():
    body = ReservationCreate(slot_id=7, party_size=2, contact_phone="  010-1234-5678  ")

    assert body.contact_phone == "010-1234-5678"


# 공백만 보낸 연락처는 안 보낸 것으로 본다
def test_reservation_create_blank_contact_phone_becomes_none():
    body = ReservationCreate(slot_id=7, party_size=2, contact_phone="   ")

    assert body.contact_phone is None


# 연락처는 20자까지만 받는다
def test_reservation_create_rejects_long_contact_phone():
    with pytest.raises(ValidationError):
        ReservationCreate(slot_id=7, party_size=2, contact_phone="0" * 21)


# 슬롯 번호는 1부터라서 0이면 막힌다
def test_reservation_create_rejects_zero_slot_id():
    with pytest.raises(ValidationError):
        ReservationCreate(slot_id=0, party_size=2)


# DB(BIGINT)에 못 담는 슬롯 번호면 막힌다
def test_reservation_create_rejects_too_big_slot_id():
    with pytest.raises(ValidationError):
        ReservationCreate(slot_id=9223372036854775808, party_size=2)
