# [담당 4] 예약 도메인 규칙 테스트 : 생성, 취소, 취소 가능 여부
import uuid
from datetime import datetime

import pytest

from auth.domain.value_object import AuthenticatedUser, AuthRole
from common.schemas import SEOUL
from reservation.domain.exceptions import (
    AlreadyCancelledError,
    CancellationNotAllowedError,
)
from reservation.domain.reservation import Reservation, ReservationStatus
from restaurant.domain.restaurant import Restaurant

NOW = datetime(2026, 11, 3, 6, 0, tzinfo=SEOUL)
SLOT_STARTS_AT = datetime(2026, 11, 3, 9, 0, tzinfo=SEOUL)
USER_ID = uuid.UUID("00000000-0000-4000-8000-000000000001")
OTHER_USER_ID = uuid.UUID("00000000-0000-4000-8000-000000000002")
OWNER_ID = uuid.UUID("00000000-0000-4000-8000-000000000003")
OTHER_OWNER_ID = uuid.UUID("00000000-0000-4000-8000-000000000004")
ADMIN_ID = uuid.UUID("00000000-0000-4000-8000-000000000005")

ME = AuthenticatedUser(user_id=USER_ID, role=AuthRole.CUSTOMER)  # 예약한 손님(나)
OWNER = AuthenticatedUser(user_id=OWNER_ID, role=AuthRole.OWNER)  # 1번 식당 주인
OTHER_OWNER = AuthenticatedUser(user_id=OTHER_OWNER_ID, role=AuthRole.OWNER)
ADMIN = AuthenticatedUser(user_id=ADMIN_ID, role=AuthRole.ADMIN)

# 1번 식당 (주인은 OWNER_ID)
RESTAURANT = Restaurant(
    id=1, owner_id=OWNER_ID, name="테스트 식당", address="서울 중구", cuisine="한식"
)


def test_create_starts_confirmed():
    reservation = Reservation.create(user_id=USER_ID, slot_id=7, party_size=2, now=NOW)

    # 새 예약은 확정 상태이고, 취소 시각은 비어 있다.
    assert reservation.status is ReservationStatus.CONFIRMED
    assert reservation.created_at == NOW
    assert reservation.cancelled_at is None


def test_cancel_marks_cancelled_with_time():
    reservation = Reservation.create(user_id=USER_ID, slot_id=7, party_size=2, now=NOW)

    reservation.cancel(slot_starts_at=SLOT_STARTS_AT, now=NOW)

    # 취소하면 상태가 바뀌고 취소 시각이 남는다.
    assert reservation.status is ReservationStatus.CANCELLED
    assert reservation.cancelled_at == NOW


def test_cancel_twice_raises_already_cancelled():
    reservation = Reservation.create(user_id=USER_ID, slot_id=7, party_size=2, now=NOW)

    # 이미 취소된 상태를 만든다.
    reservation.cancel(slot_starts_at=SLOT_STARTS_AT, now=NOW)

    # 한 번 더 취소하면 에러가 나야 한다.
    with pytest.raises(AlreadyCancelledError):
        reservation.cancel(slot_starts_at=SLOT_STARTS_AT, now=NOW)


def test_cancel_after_slot_started_raises_not_allowed():
    reservation = Reservation.create(user_id=USER_ID, slot_id=7, party_size=2, now=NOW)

    # 슬롯이 시작된 순간부터는 확정 예약이어도 취소하면 에러가 나야 한다.
    with pytest.raises(CancellationNotAllowedError):
        reservation.cancel(slot_starts_at=SLOT_STARTS_AT, now=SLOT_STARTS_AT)


def test_can_cancel_true_for_owner_confirmed():
    reservation = Reservation.create(user_id=USER_ID, slot_id=7, party_size=2, now=NOW)

    # 예약한 본인이 요청하면 취소할 수 있어야 한다.
    assert (
        reservation.can_cancel(viewer=ME, slot_starts_at=SLOT_STARTS_AT, now=NOW)
        is True
    )


def test_can_cancel_false_for_other_user():
    reservation = Reservation.create(
        user_id=OTHER_USER_ID, slot_id=7, party_size=2, now=NOW
    )

    # 다른 사람이 요청하면 취소할 수 없어야 한다.
    assert (
        reservation.can_cancel(viewer=ME, slot_starts_at=SLOT_STARTS_AT, now=NOW)
        is False
    )


def test_can_cancel_false_when_already_cancelled():
    reservation = Reservation.create(user_id=USER_ID, slot_id=7, party_size=2, now=NOW)

    reservation.cancel(slot_starts_at=SLOT_STARTS_AT, now=NOW)

    # 취소된 예약은 본인이어도 취소할 수 없어야 한다.
    assert (
        reservation.can_cancel(viewer=ME, slot_starts_at=SLOT_STARTS_AT, now=NOW)
        is False
    )


def test_can_cancel_false_when_slot_started():
    reservation = Reservation.create(user_id=USER_ID, slot_id=7, party_size=2, now=NOW)

    # 슬롯이 시작된 순간부터는 본인이어도 취소 할 수 없어야 한다.
    assert (
        reservation.can_cancel(
            viewer=ME, slot_starts_at=SLOT_STARTS_AT, now=SLOT_STARTS_AT
        )
        is False
    )


def make_reservation() -> Reservation:
    return Reservation.create(user_id=USER_ID, slot_id=7, party_size=2, now=NOW)


# 예약자 본인은 취소할 수 있다
def test_can_be_cancelled_by_reservation_owner():
    me = AuthenticatedUser(user_id=USER_ID, role=AuthRole.CUSTOMER)

    assert make_reservation().can_be_cancelled_by(me, RESTAURANT.owner_id) is True


# 다른 손님은 취소할 수 없다
def test_cannot_be_cancelled_by_other_customer():
    other = AuthenticatedUser(user_id=OTHER_USER_ID, role=AuthRole.CUSTOMER)

    assert make_reservation().can_be_cancelled_by(other, RESTAURANT.owner_id) is False


# 그 식당의 운영자는 손님 예약을 취소할 수 있다
def test_can_be_cancelled_by_restaurant_owner():
    owner = AuthenticatedUser(user_id=OWNER_ID, role=AuthRole.OWNER)

    assert make_reservation().can_be_cancelled_by(owner, RESTAURANT.owner_id) is True


# 다른 식당의 운영자는 취소할 수 없다
def test_cannot_be_cancelled_by_other_restaurant_owner():
    other_owner = AuthenticatedUser(user_id=OTHER_OWNER_ID, role=AuthRole.OWNER)

    assert (
        make_reservation().can_be_cancelled_by(other_owner, RESTAURANT.owner_id)
        is False
    )


# 운영자 역할이 아니면 식당 주인 id와 같아도 운영자로 보지 않는다
def test_cannot_be_cancelled_by_customer_with_owner_id():
    not_owner = AuthenticatedUser(user_id=OWNER_ID, role=AuthRole.CUSTOMER)

    assert (
        make_reservation().can_be_cancelled_by(not_owner, RESTAURANT.owner_id) is False
    )


# 관리자는 어느 식당 예약이든 취소할 수 있다
def test_can_be_cancelled_by_admin():
    admin = AuthenticatedUser(user_id=ADMIN_ID, role=AuthRole.ADMIN)

    assert make_reservation().can_be_cancelled_by(admin, RESTAURANT.owner_id) is True


# 그 식당 운영자가 보면 손님 예약도 취소 버튼이 보인다
def test_can_cancel_true_for_restaurant_owner():
    assert (
        make_reservation().can_cancel(
            viewer=OWNER,
            slot_starts_at=SLOT_STARTS_AT,
            now=NOW,
            restaurant_owner_id=OWNER_ID,
        )
        is True
    )


# 다른 식당 운영자가 보면 취소 버튼이 보이지 않는다
def test_can_cancel_false_for_other_restaurant_owner():
    assert (
        make_reservation().can_cancel(
            viewer=OTHER_OWNER,
            slot_starts_at=SLOT_STARTS_AT,
            now=NOW,
            restaurant_owner_id=OWNER_ID,
        )
        is False
    )


# 식당 주인을 모르면(None) 운영자 권한으로 보지 않는다
def test_can_cancel_false_for_owner_without_restaurant_owner_id():
    assert (
        make_reservation().can_cancel(
            viewer=OWNER, slot_starts_at=SLOT_STARTS_AT, now=NOW
        )
        is False
    )


# 관리자가 보면 어느 예약이든 취소 버튼이 보인다
def test_can_cancel_true_for_admin():
    assert (
        make_reservation().can_cancel(
            viewer=ADMIN, slot_starts_at=SLOT_STARTS_AT, now=NOW
        )
        is True
    )


# 운영자·관리자여도 시작 시각이 지나거나 이미 취소된 예약은 버튼이 보이지 않는다
def test_can_cancel_false_for_admin_and_owner_after_start_or_cancelled():
    started = make_reservation()
    cancelled = make_reservation()
    cancelled.cancel(slot_starts_at=SLOT_STARTS_AT, now=NOW)

    for viewer in (ADMIN, OWNER):
        assert (
            started.can_cancel(
                viewer=viewer,
                slot_starts_at=SLOT_STARTS_AT,
                now=SLOT_STARTS_AT,
                restaurant_owner_id=OWNER_ID,
            )
            is False
        )
        assert (
            cancelled.can_cancel(
                viewer=viewer,
                slot_starts_at=SLOT_STARTS_AT,
                now=NOW,
                restaurant_owner_id=OWNER_ID,
            )
            is False
        )
