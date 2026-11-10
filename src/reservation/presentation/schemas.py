# [담당 4] 예약 요청.응답 모양 : 손님이 보내는 예약 신청서와 API로 내보내는 예약 정보
import uuid
from datetime import datetime, timedelta
from typing import Annotated

from pydantic import BaseModel, Field, field_validator

from auth.domain.value_object import AuthenticatedUser
from common.errors import InvalidInputError
from common.schemas import SEOUL
from reservation.domain.reservation import (
    DEFAULT_NO_SHOW_GRACE,
    CancelledBy,
    CancelReason,
    Reservation,
    ReservationStatus,
)
from reservation.domain.value_object import ContactPhone
from slot.domain.time_slot import TimeSlot

# BIGINT 최댓값. 이보다 큰 id는 DB 오류(500) 대신 422로 막음
BIGINT_MAX = 9223372036854775807

# DB의 BIGINT id 칸에 들어갈 번호. 글자("7"), 소수(7.0), true는 정수로 바꾸지 않고 막는다
BigIntId = Annotated[int, Field(strict=True, ge=1, le=BIGINT_MAX)]


class ReservationCreate(BaseModel):
    """예약 생성 요청 스키마 (손님이 보내는 본문)"""

    slot_id: Annotated[BigIntId, Field(examples=[7], description="예약할 슬롯 ID")]
    party_size: Annotated[
        int, Field(strict=True, ge=1, examples=[2], description="예약 인원 (1명 이상)")
    ]
    contact_phone: Annotated[
        str | None,
        Field(
            max_length=20,
            examples=["010-1234-5678"],
            description="연락처(선택). 하이픈은 있어도 없어도 되고, 010-1234-5678 모양으로 저장",
        ),
    ] = None

    @field_validator("contact_phone", mode="before")
    @classmethod
    def strip_contact_phone(cls, value: object) -> object:
        # 앞뒤 공백을 지우고, 공백만 남으면 안 보낸 것(None)으로 본다
        if isinstance(value, str):
            value = value.strip()
            return value or None
        return value

    @field_validator("contact_phone", mode="after")
    @classmethod
    def format_contact_phone(cls, value: str | None) -> str | None:
        # 규칙은 도메인 값 객체(ContactPhone) 하나에 두고, 입구에서는 그걸 불러 422로 바꿔 준다
        if value is None:
            return None
        try:
            return ContactPhone(value).value
        except InvalidInputError:
            raise ValueError("휴대폰 번호 형식이 아닙니다.") from None


class ReservationOut(BaseModel):
    """예약 응답 스키마"""

    id: Annotated[int, Field(description="예약 ID")]
    user_id: Annotated[uuid.UUID, Field(description="예약한 사용자 ID")]
    slot_id: Annotated[int, Field(description="예약한 슬롯 ID")]
    restaurant_id: Annotated[int, Field(description="식당 ID")]
    starts_at: Annotated[datetime, Field(description="슬롯 시작 시각 (Asia/Seoul)")]
    ends_at: Annotated[datetime, Field(description="슬롯 종료 시각 (Asia/Seoul)")]
    party_size: Annotated[int, Field(description="예약 인원")]
    contact_phone: Annotated[
        str | None,
        Field(examples=["010-1234-5678"], description="연락처(선택)"),
    ]
    status: Annotated[
        ReservationStatus,
        Field(description="예약 상태 (CONFIRMED: 확정, CANCELLED: 취소)"),
    ]
    created_at: Annotated[datetime, Field(description="예약한 시각")]
    cancelled_at: Annotated[
        datetime | None, Field(description="취소한 시각 (취소 전에는 null)")
    ]
    can_cancel: Annotated[
        bool,
        Field(
            description="취소 가능 여부. 보는 사람이 예약자 본인·관리자·그 식당 운영자이고, 확정 상태이고, 슬롯 시작 전이면 true"
        ),
    ]
    cancelled_by: Annotated[
        CancelledBy | None,
        Field(
            description="누가 취소했나 (CUSTOMER, OWNER, ADMIN, SYSTEM=자동 노쇼). 취소 전에는 null"
        ),
    ] = None
    cancel_reason: Annotated[
        CancelReason | None,
        Field(description="왜 취소했나 (NO_SHOW면 노쇼). 취소 전에는 null"),
    ] = None
    cancel_note: Annotated[
        str | None,
        Field(
            description="취소 메모 (내부용). 관리자와 그 식당 운영자에게만 보이고, 손님에게는 null"
        ),
    ] = None
    checked_in_at: Annotated[
        datetime | None,
        Field(description="운영자가 입장 확인한 시각 (Asia/Seoul). 안 왔으면 null"),
    ] = None
    can_check_in: Annotated[
        bool,
        Field(
            description="입장 버튼 표시 여부. 그 식당 운영자이고, 확정·미입장이고, 시작 30분 전 ~ 끝나기 전이면 true"
        ),
    ] = False
    can_mark_no_show: Annotated[
        bool,
        Field(
            description="노쇼 버튼 표시 여부. 그 식당 운영자이고, 확정·미입장이고, 시작 + 유예 시간이 지났으면 true"
        ),
    ] = False

    @classmethod
    def from_domain(
        cls,
        reservation: Reservation,
        slot: TimeSlot,
        viewer: AuthenticatedUser,
        now: datetime,
        restaurant_owner_id: uuid.UUID | None = None,
        no_show_grace: timedelta = DEFAULT_NO_SHOW_GRACE,
    ) -> ReservationOut:
        """도메인 Reservation + TimeSlot -> 응답 DTO. 시각 칸은 서울 시간으로 바꿔 넣고, 버튼 표시·메모 공개는 도메인에 물어서 채운다.
        viewer는 보는 사람(역할까지), restaurant_owner_id는 그 식당 주인. 운영자에게 버튼·메모를 보여 줄 때 필요하다."""
        # DB에서 꺼낸 시각은 UTC라서, 응답에서는 같은 순간을 서울 시계(+09:00)로 다시 읽어 내보낸다
        cancelled_at = reservation.cancelled_at
        checked_in_at = reservation.checked_in_at
        return cls(
            id=reservation.id,
            user_id=reservation.user_id,
            slot_id=reservation.slot_id,
            restaurant_id=slot.restaurant_id,
            starts_at=slot.starts_at.astimezone(SEOUL),
            ends_at=slot.ends_at.astimezone(SEOUL),
            party_size=reservation.party_size,
            contact_phone=reservation.contact_phone,
            status=reservation.status,
            created_at=reservation.created_at.astimezone(SEOUL),
            cancelled_at=cancelled_at.astimezone(SEOUL) if cancelled_at else None,
            can_cancel=reservation.can_cancel(
                viewer=viewer,
                slot_starts_at=slot.starts_at,
                now=now,
                restaurant_owner_id=restaurant_owner_id,
            ),
            cancelled_by=reservation.cancelled_by,
            cancel_reason=reservation.cancel_reason,
            # 내부 메모는 관리자·그 식당 운영자에게만. 손님에게는 숨긴다
            cancel_note=(
                reservation.cancel_note
                if reservation.can_see_cancel_note(viewer, restaurant_owner_id)
                else None
            ),
            checked_in_at=checked_in_at.astimezone(SEOUL) if checked_in_at else None,
            can_check_in=reservation.can_check_in(
                viewer, now, slot.starts_at, slot.ends_at, restaurant_owner_id
            ),
            can_mark_no_show=reservation.can_mark_no_show(
                viewer, now, slot.starts_at, no_show_grace, restaurant_owner_id
            ),
        )


class ReservationCancelRequest(BaseModel):
    """운영자·관리자 취소 신청서. 어떤 이유를 쓸 수 있는지는 도메인이 역할별로 판단한다 (안 맞으면 422)."""

    reason: Annotated[
        CancelReason,
        Field(
            examples=["PHONE_REQUEST"],
            description="취소 이유. 운영자: PHONE_REQUEST, RESTAURANT_ISSUE, OTHER, NO_SHOW / 관리자: SYSTEM_ERROR, OTHER",
        ),
    ]
    note: Annotated[
        str | None,
        Field(max_length=100, description="메모 (100자 이하). 관리자는 필수"),
    ] = None

    @field_validator("note", mode="before")
    @classmethod
    def strip_note(cls, value: object) -> object:
        # 앞뒤 공백을 지우고, 공백만 남으면 메모 없음(None)으로 본다
        if isinstance(value, str):
            value = value.strip()
            return value or None
        return value
