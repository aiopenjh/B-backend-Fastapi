# [담당 4] 예약 응답 스키마 테스트 : API 명세 예시, from_domain 변환, can_cancel 값, 보는 사람을 Actor로 바꾸기
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from auth.domain.value_object import AuthenticatedUser, AuthRole
from common.schemas import SEOUL
from reservation.domain.reservation import (
    CancelledBy,
    CancelReason,
    Reservation,
    ReservationStatus,
)
from reservation.domain.value_object import Actor
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
RESTAURANT_OWNER_ID = uuid.UUID("00000000-0000-4000-8000-000000000003")
ADMIN_ID = uuid.UUID("00000000-0000-4000-8000-000000000005")

RESERVER = AuthenticatedUser(user_id=OWNER_ID, role=AuthRole.CUSTOMER)  # 예약한 손님
GUEST = AuthenticatedUser(user_id=GUEST_ID, role=AuthRole.CUSTOMER)  # 다른 손님
RESTAURANT_OWNER = AuthenticatedUser(user_id=RESTAURANT_OWNER_ID, role=AuthRole.OWNER)
ADMIN = AuthenticatedUser(user_id=ADMIN_ID, role=AuthRole.ADMIN)
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

    out = ReservationOut.from_domain(reservation, slot, RESERVER, NOW)

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
    out = ReservationOut.from_domain(reservation, slot, GUEST, NOW)

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

    out = ReservationOut.from_domain(reservation, slot, RESERVER, NOW)

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

    out = ReservationOut.from_domain(reservation, slot, RESERVER, STARTS_AT)

    assert out.can_cancel is False


def make_confirmed() -> tuple[Reservation, TimeSlot]:
    reservation = Reservation(
        id=3,
        user_id=OWNER_ID,
        slot_id=7,
        party_size=2,
        status=ReservationStatus.CONFIRMED,
        created_at=CREATED_AT,
    )
    return reservation, TimeSlot(**TIME_SLOT_EXAMPLE)


# 그 식당 운영자가 보면 손님 예약도 can_cancel은 True
def test_from_domain_can_cancel_true_for_restaurant_owner():
    reservation, slot = make_confirmed()

    out = ReservationOut.from_domain(
        reservation,
        slot,
        RESTAURANT_OWNER,
        NOW,
        restaurant_owner_id=RESTAURANT_OWNER_ID,
    )

    assert out.can_cancel is True


# 운영자라도 식당 주인을 모르면(넘기지 않으면) can_cancel은 False
def test_from_domain_can_cancel_false_for_owner_without_restaurant_owner_id():
    reservation, slot = make_confirmed()

    out = ReservationOut.from_domain(reservation, slot, RESTAURANT_OWNER, NOW)

    assert out.can_cancel is False


# 관리자가 보면 can_cancel은 True
def test_from_domain_can_cancel_true_for_admin():
    reservation, slot = make_confirmed()

    out = ReservationOut.from_domain(reservation, slot, ADMIN, NOW)

    assert out.can_cancel is True


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

    body = ReservationOut.from_domain(reservation, slot, RESERVER, NOW).model_dump(
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


# 슬롯 번호는 진짜 정수만 받는다 (글자, 소수, true를 정수로 바꿔 주지 않는다)
@pytest.mark.parametrize("slot_id", ["7", 7.0, True])
def test_reservation_create_rejects_non_int_slot_id(slot_id):
    with pytest.raises(ValidationError):
        ReservationCreate(slot_id=slot_id, party_size=2)


# 인원도 진짜 정수만 받는다 (true가 1명이 되면 안 된다)
@pytest.mark.parametrize("party_size", ["2", 2.0, True])
def test_reservation_create_rejects_non_int_party_size(party_size):
    with pytest.raises(ValidationError):
        ReservationCreate(slot_id=7, party_size=party_size)


# 연락처는 휴대폰 번호 모양만 받는다 (글자, 이모지, NUL, 다른 나라 숫자는 막는다)
@pytest.mark.parametrize(
    "contact_phone",
    ["abc", "!!!!", "😀", "010\x001234", "010-١٢٣٤-٥٦٧٨", "02-123-4567", "0101234567"],
)
def test_reservation_create_rejects_non_phone_contact(contact_phone):
    with pytest.raises(ValidationError):
        ReservationCreate(slot_id=7, party_size=2, contact_phone=contact_phone)


# 하이픈은 있어도 없어도 받고, 저장할 모양은 항상 010-1234-5678로 맞춘다
@pytest.mark.parametrize(
    ("contact_phone", "expected"),
    [
        ("010-1234-5678", "010-1234-5678"),
        ("01012345678", "010-1234-5678"),
        ("010-12345678", "010-1234-5678"),
        ("0101234-5678", "010-1234-5678"),
        ("  01012345678  ", "010-1234-5678"),
        ("0111234567", "011-123-4567"),
        ("011-123-4567", "011-123-4567"),
    ],
)
def test_reservation_create_formats_contact_phone(contact_phone, expected):
    body = ReservationCreate(slot_id=7, party_size=2, contact_phone=contact_phone)

    assert body.contact_phone == expected


def make_cancelled_with_note() -> tuple[Reservation, TimeSlot]:
    reservation, slot = make_confirmed()
    reservation.cancel(
        slot_starts_at=STARTS_AT,
        now=NOW,
        by=CancelledBy.ADMIN,
        reason=CancelReason.OTHER,
        note="내부 메모: 블랙리스트 확인",
    )
    return reservation, slot


# 취소 메모는 내부용이라 손님(예약한 본인)에게는 숨긴다
def test_from_domain_hides_cancel_note_from_customer():
    reservation, slot = make_cancelled_with_note()

    out = ReservationOut.from_domain(
        reservation, slot, RESERVER, NOW, restaurant_owner_id=RESTAURANT_OWNER_ID
    )

    assert out.cancel_note is None
    assert out.cancel_reason is CancelReason.OTHER  # 이유는 손님도 볼 수 있다


# 관리자와 그 식당 운영자는 취소 메모를 본다
def test_from_domain_shows_cancel_note_to_admin_and_owner():
    reservation, slot = make_cancelled_with_note()

    to_admin = ReservationOut.from_domain(reservation, slot, ADMIN, NOW)
    to_owner = ReservationOut.from_domain(
        reservation,
        slot,
        RESTAURANT_OWNER,
        NOW,
        restaurant_owner_id=RESTAURANT_OWNER_ID,
    )

    assert to_admin.cancel_note == "내부 메모: 블랙리스트 확인"
    assert to_owner.cancel_note == "내부 메모: 블랙리스트 확인"


# 응답에 입장·노쇼 버튼 표시가 들어간다 (그 식당 운영자에게만 true)
def test_from_domain_check_in_and_no_show_flags():
    reservation, slot = make_confirmed()
    at_start = STARTS_AT
    after_grace = STARTS_AT + timedelta(minutes=15)

    owner_at_start = ReservationOut.from_domain(
        reservation,
        slot,
        RESTAURANT_OWNER,
        at_start,
        restaurant_owner_id=RESTAURANT_OWNER_ID,
    )
    owner_after = ReservationOut.from_domain(
        reservation,
        slot,
        RESTAURANT_OWNER,
        after_grace,
        restaurant_owner_id=RESTAURANT_OWNER_ID,
    )
    customer_after = ReservationOut.from_domain(
        reservation,
        slot,
        RESERVER,
        after_grace,
        restaurant_owner_id=RESTAURANT_OWNER_ID,
    )

    assert owner_at_start.can_check_in is True
    assert owner_at_start.can_mark_no_show is False  # 아직 15분 안 지남
    assert owner_after.can_mark_no_show is True
    assert customer_after.can_check_in is False
    assert customer_after.can_mark_no_show is False


# from_domain은 로그인한 사람(AuthenticatedUser)을 받아도, 도메인에 물을 때는 예약 쪽 Actor로 바꿔서 묻는다
@pytest.mark.parametrize("viewer", [RESERVER, GUEST, RESTAURANT_OWNER, ADMIN])
def test_from_domain_asks_domain_with_actor(viewer, monkeypatch):
    reservation, slot = make_cancelled_with_note()
    seen = []
    original = Reservation.can_see_cancel_note

    def spy(self, who, restaurant_owner_id):
        seen.append(who)
        return original(self, who, restaurant_owner_id)

    monkeypatch.setattr(Reservation, "can_see_cancel_note", spy)

    from_login = ReservationOut.from_domain(
        reservation, slot, viewer, NOW, restaurant_owner_id=RESTAURANT_OWNER_ID
    )
    from_actor = ReservationOut.from_domain(
        reservation,
        slot,
        Actor(viewer.user_id, viewer.role),
        NOW,
        restaurant_owner_id=RESTAURANT_OWNER_ID,
    )

    # 도메인은 두 번 모두 진짜 Actor를 받았고, 응답도 똑같다
    assert [type(who) for who in seen] == [Actor, Actor]
    assert from_login == from_actor
