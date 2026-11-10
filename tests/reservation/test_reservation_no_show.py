# [담당 4] 예약 노쇼·취소 이유 도메인 테스트 : 누가·왜 취소하는지, 노쇼 시각, 입장 확인
import uuid
from datetime import datetime, timedelta

import pytest

from common.schemas import SEOUL
from reservation.domain.exceptions import (
    AlreadyCancelledError,
    AlreadyCheckedInError,
    CancellationNotAllowedError,
    CancelNoteRequiredError,
    CancelReasonNotAllowedError,
    CheckInNotAllowedError,
    NoShowTooEarlyError,
)
from reservation.domain.reservation import (
    CancelledBy,
    CancelReason,
    Reservation,
    ReservationStatus,
)

USER_ID = uuid.UUID("00000000-0000-4000-8000-000000000001")
STARTS_AT = datetime(2026, 12, 3, 16, 0, tzinfo=SEOUL)  # 4시 슬롯
ENDS_AT = datetime(2026, 12, 3, 17, 0, tzinfo=SEOUL)
BEFORE = STARTS_AT - timedelta(hours=1)  # 시작 1시간 전
GRACE = timedelta(minutes=15)  # 노쇼 유예 시간


def make_reservation() -> Reservation:
    return Reservation.create(user_id=USER_ID, slot_id=7, party_size=2, now=BEFORE)


# 손님 취소는 예전과 같다: 이유는 손님 요청, 누가는 손님으로 남는다
def test_customer_cancel_records_who_and_why():
    reservation = make_reservation()

    reservation.cancel(slot_starts_at=STARTS_AT, now=BEFORE)

    assert reservation.status is ReservationStatus.CANCELLED
    assert reservation.cancelled_by is CancelledBy.CUSTOMER
    assert reservation.cancel_reason is CancelReason.CUSTOMER_REQUEST


# 운영자는 전화 요청·식당 사정·기타 이유로 시작 전에 취소할 수 있다
@pytest.mark.parametrize(
    "reason",
    [CancelReason.PHONE_REQUEST, CancelReason.RESTAURANT_ISSUE, CancelReason.OTHER],
)
def test_owner_cancels_before_start_with_owner_reason(reason):
    reservation = make_reservation()

    reservation.cancel(
        slot_starts_at=STARTS_AT, now=BEFORE, by=CancelledBy.OWNER, reason=reason
    )

    assert reservation.cancelled_by is CancelledBy.OWNER
    assert reservation.cancel_reason is reason


# 역할에 맞지 않는 이유는 422 (예: 운영자가 '시스템 오류', 손님이 '노쇼')
@pytest.mark.parametrize(
    ("by", "reason"),
    [
        (CancelledBy.OWNER, CancelReason.SYSTEM_ERROR),
        (CancelledBy.OWNER, CancelReason.CUSTOMER_REQUEST),
        (CancelledBy.CUSTOMER, CancelReason.NO_SHOW),
        (CancelledBy.ADMIN, CancelReason.NO_SHOW),
        (CancelledBy.SYSTEM, CancelReason.OTHER),
    ],
)
def test_reason_not_allowed_for_role(by, reason):
    with pytest.raises(CancelReasonNotAllowedError):
        make_reservation().cancel(
            slot_starts_at=STARTS_AT, now=BEFORE, by=by, reason=reason, note="메모"
        )


# 운영자의 일반 취소도 시작 후에는 409
def test_owner_normal_cancel_after_start_is_not_allowed():
    with pytest.raises(CancellationNotAllowedError):
        make_reservation().cancel(
            slot_starts_at=STARTS_AT,
            now=STARTS_AT,
            by=CancelledBy.OWNER,
            reason=CancelReason.PHONE_REQUEST,
        )


# 노쇼는 시작 + 15분부터 된다 (경계값: 14분 59초는 409, 정확히 15분은 노쇼)
def test_no_show_boundary_at_grace():
    early = make_reservation()
    with pytest.raises(NoShowTooEarlyError):
        early.cancel(
            slot_starts_at=STARTS_AT,
            now=STARTS_AT + GRACE - timedelta(seconds=1),
            by=CancelledBy.OWNER,
            reason=CancelReason.NO_SHOW,
            grace=GRACE,
        )

    on_time = make_reservation()
    on_time.cancel(
        slot_starts_at=STARTS_AT,
        now=STARTS_AT + GRACE,
        by=CancelledBy.OWNER,
        reason=CancelReason.NO_SHOW,
        grace=GRACE,
    )
    assert on_time.cancel_reason is CancelReason.NO_SHOW


# 시스템(자동)도 같은 시각 규칙으로 노쇼 처리한다
def test_system_marks_no_show():
    reservation = make_reservation()

    reservation.cancel(
        slot_starts_at=STARTS_AT,
        now=STARTS_AT + GRACE,
        by=CancelledBy.SYSTEM,
        reason=CancelReason.NO_SHOW,
        grace=GRACE,
    )

    assert reservation.cancelled_by is CancelledBy.SYSTEM
    assert reservation.cancel_reason is CancelReason.NO_SHOW


# 입장 확인된 예약은 노쇼로 처리할 수 없다
def test_no_show_after_check_in_is_not_allowed():
    reservation = make_reservation()
    reservation.check_in(now=STARTS_AT, slot_starts_at=STARTS_AT, slot_ends_at=ENDS_AT)

    with pytest.raises(AlreadyCheckedInError):
        reservation.cancel(
            slot_starts_at=STARTS_AT,
            now=STARTS_AT + GRACE,
            by=CancelledBy.OWNER,
            reason=CancelReason.NO_SHOW,
            grace=GRACE,
        )


# 관리자는 시작 후에도 취소할 수 있지만 메모가 꼭 있어야 한다
def test_admin_cancels_after_start_with_note():
    reservation = make_reservation()

    reservation.cancel(
        slot_starts_at=STARTS_AT,
        now=STARTS_AT + timedelta(hours=1),
        by=CancelledBy.ADMIN,
        reason=CancelReason.SYSTEM_ERROR,
        note="  결제 오류로 취소  ",
    )

    assert reservation.cancelled_by is CancelledBy.ADMIN
    assert reservation.cancel_note == "결제 오류로 취소"  # 앞뒤 공백은 지운다


# 관리자가 메모 없이(또는 공백만) 취소하면 422
@pytest.mark.parametrize("note", [None, "", "   "])
def test_admin_cancel_without_note_is_rejected(note):
    with pytest.raises(CancelNoteRequiredError):
        make_reservation().cancel(
            slot_starts_at=STARTS_AT,
            now=BEFORE,
            by=CancelledBy.ADMIN,
            reason=CancelReason.OTHER,
            note=note,
        )


# 이미 취소된 예약은 누가 어떤 이유로든 409
def test_cancelled_reservation_cannot_be_cancelled_again():
    reservation = make_reservation()
    reservation.cancel(slot_starts_at=STARTS_AT, now=BEFORE)

    with pytest.raises(AlreadyCancelledError):
        reservation.cancel(
            slot_starts_at=STARTS_AT,
            now=STARTS_AT + GRACE,
            by=CancelledBy.SYSTEM,
            reason=CancelReason.NO_SHOW,
            grace=GRACE,
        )


# 시작 전에 취소했을 때만 좌석을 돌려준다 (노쇼·시작 후 관리자 취소는 안 돌려줌)
def test_returns_seat_only_when_cancelled_before_start():
    before = make_reservation()
    before.cancel(slot_starts_at=STARTS_AT, now=BEFORE)

    no_show = make_reservation()
    no_show.cancel(
        slot_starts_at=STARTS_AT,
        now=STARTS_AT + GRACE,
        by=CancelledBy.SYSTEM,
        reason=CancelReason.NO_SHOW,
        grace=GRACE,
    )

    assert before.returns_seat(STARTS_AT) is True
    assert no_show.returns_seat(STARTS_AT) is False
    assert make_reservation().returns_seat(STARTS_AT) is False  # 취소 안 한 예약


# 입장 확인은 시작 30분 전부터 끝나기 전까지 (경계값 포함)
def test_check_in_window():
    opens = make_reservation()
    opens.check_in(
        now=STARTS_AT - timedelta(minutes=30),
        slot_starts_at=STARTS_AT,
        slot_ends_at=ENDS_AT,
    )
    assert opens.checked_in_at == STARTS_AT - timedelta(minutes=30)

    for now in (STARTS_AT - timedelta(minutes=31), ENDS_AT):
        with pytest.raises(CheckInNotAllowedError):
            make_reservation().check_in(
                now=now, slot_starts_at=STARTS_AT, slot_ends_at=ENDS_AT
            )


# 입장 확인을 두 번 하거나, 취소된 예약을 입장 확인하면 409
def test_check_in_twice_or_cancelled_is_rejected():
    twice = make_reservation()
    twice.check_in(now=STARTS_AT, slot_starts_at=STARTS_AT, slot_ends_at=ENDS_AT)
    with pytest.raises(AlreadyCheckedInError):
        twice.check_in(now=STARTS_AT, slot_starts_at=STARTS_AT, slot_ends_at=ENDS_AT)

    cancelled = make_reservation()
    cancelled.cancel(slot_starts_at=STARTS_AT, now=BEFORE)
    with pytest.raises(AlreadyCancelledError):
        cancelled.check_in(
            now=STARTS_AT, slot_starts_at=STARTS_AT, slot_ends_at=ENDS_AT
        )
