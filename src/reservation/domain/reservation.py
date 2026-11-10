# [담당 4] 예약 도메인 : 예약 규칙 (생성, 취소, 노쇼, 입장 확인, 취소 가능 여부)
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Self

from auth.domain.value_object import AuthenticatedUser
from common.errors import InvalidInputError
from reservation.domain.exceptions import (
    AlreadyCancelledError,
    AlreadyCheckedInError,
    CancellationNotAllowedError,
    CancelNoteRequiredError,
    CancelReasonNotAllowedError,
    CheckInNotAllowedError,
    NoShowTooEarlyError,
)
from reservation.domain.value_object import ContactPhone

# 시작 후 이만큼 지나도 입장 확인이 없으면 노쇼로 볼 수 있다 (매니저가 환경변수 값으로 바꿔 넘긴다)
DEFAULT_NO_SHOW_GRACE = timedelta(minutes=15)
# 입장 확인은 시작 이만큼 전부터 받는다
CHECK_IN_OPENS_BEFORE = timedelta(minutes=30)
CANCEL_NOTE_MAX = 100


class ReservationStatus(StrEnum):
    """예약 상태. 확정과 취소 두가지이고, DB에는 문자열로 저장한다. 노쇼는 상태가 아니라 취소 이유(NO_SHOW)로 구분한다."""

    CONFIRMED = "CONFIRMED"
    CANCELLED = "CANCELLED"


class CancelledBy(StrEnum):
    """누가 취소했나. SYSTEM은 자동 노쇼 처리."""

    CUSTOMER = "CUSTOMER"
    OWNER = "OWNER"
    ADMIN = "ADMIN"
    SYSTEM = "SYSTEM"


class CancelReason(StrEnum):
    """왜 취소했나."""

    CUSTOMER_REQUEST = "CUSTOMER_REQUEST"  # 손님이 직접 취소
    PHONE_REQUEST = "PHONE_REQUEST"  # 손님이 전화로 부탁해서 운영자가 취소
    RESTAURANT_ISSUE = "RESTAURANT_ISSUE"  # 식당 사정
    NO_SHOW = "NO_SHOW"  # 안 옴
    SYSTEM_ERROR = "SYSTEM_ERROR"  # 시스템 오류 정리 (관리자)
    OTHER = "OTHER"


# 역할마다 쓸 수 있는 취소 이유
ALLOWED_REASONS: dict[CancelledBy, frozenset[CancelReason]] = {
    CancelledBy.CUSTOMER: frozenset({CancelReason.CUSTOMER_REQUEST}),
    CancelledBy.OWNER: frozenset(
        {
            CancelReason.PHONE_REQUEST,
            CancelReason.RESTAURANT_ISSUE,
            CancelReason.OTHER,
            CancelReason.NO_SHOW,
        }
    ),
    CancelledBy.ADMIN: frozenset({CancelReason.SYSTEM_ERROR, CancelReason.OTHER}),
    CancelledBy.SYSTEM: frozenset({CancelReason.NO_SHOW}),
}


@dataclass
class Reservation:
    """예약 한 건. 누가(user_id) 어느 슬롯(slot_id)을 몇 명(party_size)으로 예약했는지와 상태를 가진다."""

    user_id: uuid.UUID
    slot_id: int
    party_size: int
    status: ReservationStatus
    created_at: datetime
    contact_phone: str | None = None
    cancelled_at: datetime | None = None
    id: int | None = None
    cancelled_by: CancelledBy | None = None
    cancel_reason: CancelReason | None = None
    cancel_note: str | None = None
    checked_in_at: datetime | None = None  # 운영자가 "입장"을 누른 시각

    @classmethod
    def create(
        cls,
        user_id: uuid.UUID,
        slot_id: int,
        party_size: int,
        now: datetime,
        contact_phone: str | None = None,
    ) -> Self:
        """새 예약을 만든다. 대기 상태 없이 항상 확정(CONFIRMED)으로 시작한다. 연락처는 ContactPhone 규칙으로 모양을 맞춘다."""
        # 글자면 앞뒤 공백을 지우고, 비어 있으면 안 보낸 것(None)으로 본다
        phone = (
            contact_phone.strip() if isinstance(contact_phone, str) else contact_phone
        )
        return cls(
            user_id=user_id,
            slot_id=slot_id,
            party_size=party_size,
            status=ReservationStatus.CONFIRMED,
            created_at=now,
            contact_phone=ContactPhone(phone).value if phone else None,
        )

    def cancel(
        self,
        slot_starts_at: datetime,
        now: datetime,
        by: CancelledBy = CancelledBy.CUSTOMER,
        reason: CancelReason = CancelReason.CUSTOMER_REQUEST,
        grace: timedelta = DEFAULT_NO_SHOW_GRACE,
        note: str | None = None,
    ) -> None:
        """예약을 취소 상태로 바꾸고 누가·왜·언제를 남긴다. 기본값은 손님 취소라 예전 호출과 결과가 같다.
        - 손님·운영자의 일반 취소: 시작 전까지만
        - 노쇼(운영자·시스템): 시작 + 유예 시간이 지나고 입장 확인이 없을 때만
        - 관리자: 시각 제한 없음, 메모 필수"""
        if self.status is ReservationStatus.CANCELLED:
            raise AlreadyCancelledError()
        if reason not in ALLOWED_REASONS[by]:
            raise CancelReasonNotAllowedError()

        clean_note = (note.strip() if note else None) or None  # 공백만이면 메모 없음
        if clean_note is not None and len(clean_note) > CANCEL_NOTE_MAX:
            raise InvalidInputError(
                errors={"note": [f"메모는 {CANCEL_NOTE_MAX}자까지 쓸 수 있습니다."]}
            )
        if by is CancelledBy.ADMIN and clean_note is None:
            raise CancelNoteRequiredError()

        if reason is CancelReason.NO_SHOW:
            if self.checked_in_at is not None:
                raise AlreadyCheckedInError()
            if now < slot_starts_at + grace:
                raise NoShowTooEarlyError()
        elif by is not CancelledBy.ADMIN and now >= slot_starts_at:
            raise CancellationNotAllowedError()

        self.status = ReservationStatus.CANCELLED
        self.cancelled_at = now
        self.cancelled_by = by
        self.cancel_reason = reason
        self.cancel_note = clean_note

    def returns_seat(self, slot_starts_at: datetime) -> bool:
        """취소로 좌석을 돌려줘야 하나. 시작 전에 취소했을 때만 True (노쇼·시작 후 관리자 취소는 이미 지난 자리라 안 돌려줌)."""
        return self.cancelled_at is not None and self.cancelled_at < slot_starts_at

    def check_in(
        self, now: datetime, slot_starts_at: datetime, slot_ends_at: datetime
    ) -> None:
        """손님이 왔다고 기록한다 (운영자의 "입장" 버튼). 확정 예약만, 시작 30분 전부터 끝나기 전까지."""
        if self.status is ReservationStatus.CANCELLED:
            raise AlreadyCancelledError()
        if self.checked_in_at is not None:
            raise AlreadyCheckedInError()
        if not (slot_starts_at - CHECK_IN_OPENS_BEFORE <= now < slot_ends_at):
            raise CheckInNotAllowedError()
        self.checked_in_at = now

    def can_cancel(
        self,
        viewer: AuthenticatedUser,
        slot_starts_at: datetime,
        now: datetime,
        restaurant_owner_id: uuid.UUID | None = None,
    ) -> bool:
        """취소 버튼을 보여 줄지 확인만 한다 (상태는 바꾸지 않음). 확정 상태이고, 슬롯 시작 전이고, 취소 권한이 있으면 True."""
        return (
            self.status is ReservationStatus.CONFIRMED
            and now < slot_starts_at
            and self._has_cancel_right(viewer, restaurant_owner_id)
        )

    def can_check_in(
        self,
        viewer: AuthenticatedUser,
        now: datetime,
        slot_starts_at: datetime,
        slot_ends_at: datetime,
        restaurant_owner_id: uuid.UUID | None = None,
    ) -> bool:
        """입장 버튼을 보여 줄지 확인만 한다. 그 식당 운영자이고, 확정·미입장이고, 입장 시간(시작 30분 전 ~ 끝나기 전)이면 True."""
        return (
            self._is_restaurant_owner(viewer, restaurant_owner_id)
            and self.status is ReservationStatus.CONFIRMED
            and self.checked_in_at is None
            and slot_starts_at - CHECK_IN_OPENS_BEFORE <= now < slot_ends_at
        )

    def can_mark_no_show(
        self,
        viewer: AuthenticatedUser,
        now: datetime,
        slot_starts_at: datetime,
        grace: timedelta = DEFAULT_NO_SHOW_GRACE,
        restaurant_owner_id: uuid.UUID | None = None,
    ) -> bool:
        """노쇼 버튼을 보여 줄지 확인만 한다. 그 식당 운영자이고, 확정·미입장이고, 시작 + 유예 시간이 지났으면 True."""
        return (
            self._is_restaurant_owner(viewer, restaurant_owner_id)
            and self.status is ReservationStatus.CONFIRMED
            and self.checked_in_at is None
            and now >= slot_starts_at + grace
        )

    def can_see_cancel_note(
        self, viewer: AuthenticatedUser, restaurant_owner_id: uuid.UUID | None
    ) -> bool:
        """취소 메모(내부용)를 볼 수 있나. 관리자와 그 식당 운영자만 True (손님에게는 숨긴다)."""
        return viewer.is_admin() or self._is_restaurant_owner(
            viewer, restaurant_owner_id
        )

    def can_be_cancelled_by(
        self, user: AuthenticatedUser, restaurant_owner_id: uuid.UUID | None
    ) -> bool:
        """취소 권한만 본다 (상태·시각·이유는 cancel이 본다). 예약자 본인, 관리자, 그 식당의 운영자면 True."""
        return self._has_cancel_right(user, restaurant_owner_id)

    def _has_cancel_right(
        self, user: AuthenticatedUser, restaurant_owner_id: uuid.UUID | None
    ) -> bool:
        # 버튼(can_cancel)과 진짜 취소(can_be_cancelled_by)가 같은 판단을 쓰도록 한 곳에 둔다
        return (
            self.user_id == user.user_id
            or user.is_admin()
            or self._is_restaurant_owner(user, restaurant_owner_id)
        )

    @staticmethod
    def _is_restaurant_owner(
        user: AuthenticatedUser, restaurant_owner_id: uuid.UUID | None
    ) -> bool:
        # 운영자 역할이고 그 식당 주인이어야 한다. 식당 주인을 모르면(None) 운영자 권한은 주지 않는다
        return (
            user.is_owner()
            and restaurant_owner_id is not None
            and restaurant_owner_id == user.user_id
        )
