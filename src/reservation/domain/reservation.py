# [담당 4] 예약 도메인 : 예약 규칙 (생성, 취소, 취소 가능 여부)
import uuid
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Self

from auth.domain.value_object import AuthenticatedUser
from reservation.domain.exceptions import (
    AlreadyCancelledError,
    CancellationNotAllowedError,
)
from restaurant.domain.restaurant import Restaurant


class ReservationStatus(StrEnum):
    """예약 상태. 확정과 취소 두가지이고, DB에는 문자열로 저장한다."""

    CONFIRMED = "CONFIRMED"
    CANCELLED = "CANCELLED"


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

    @classmethod
    def create(
        cls,
        user_id: uuid.UUID,
        slot_id: int,
        party_size: int,
        now: datetime,
        contact_phone: str | None = None,
    ) -> Self:
        """새 예약을 만든다. 대기 상태 없이 항상 확정(CONFIRMED)으로 시작한다."""
        return cls(
            user_id=user_id,
            slot_id=slot_id,
            party_size=party_size,
            status=ReservationStatus.CONFIRMED,
            created_at=now,
            contact_phone=contact_phone,
        )

    def cancel(self, slot_starts_at: datetime, now: datetime) -> None:
        """예약을 취소 상태로 바꾸고 취소 시각을 남긴다. 이미 취소된 예약이면 AlreadyCancelledError, 슬롯이 시작됐으면 CancellationNotAllowedError."""
        if self.status is ReservationStatus.CANCELLED:
            raise AlreadyCancelledError()

        if now >= slot_starts_at:
            raise CancellationNotAllowedError()

        self.status = ReservationStatus.CANCELLED
        self.cancelled_at = now

    def can_cancel(
        self, user_id: uuid.UUID, slot_starts_at: datetime, now: datetime
    ) -> bool:
        """취소할 수 있는지 확인만 한다 (상태는 바꾸지 않음). 예약자 본인이고 확정 상태이고, 슬롯 시작 전이면 True."""
        return (
            self.user_id == user_id
            and self.status is ReservationStatus.CONFIRMED
            and now < slot_starts_at
        )

    def can_be_cancelled_by(
        self, user: AuthenticatedUser, restaurant: Restaurant
    ) -> bool:
        """취소 권한만 본다 (상태·시각은 cancel이 본다). 예약자 본인, 관리자, 그 식당의 운영자면 True."""
        return (
            self.user_id == user.user_id
            or user.is_admin()
            or (user.is_owner() and restaurant.is_owned_by(user.user_id))
        )
