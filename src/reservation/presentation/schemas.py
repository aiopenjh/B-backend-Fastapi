# [담당 4] 예약 요청.응답 모양 : 손님이 보내는 예약 신청서와 API로 내보내는 예약 정보
import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, Field, field_validator

from auth.domain.value_object import AuthenticatedUser
from common.errors import InvalidInputError
from common.schemas import SEOUL
from reservation.domain.reservation import Reservation, ReservationStatus
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

    @classmethod
    def from_domain(
        cls,
        reservation: Reservation,
        slot: TimeSlot,
        viewer: AuthenticatedUser,
        now: datetime,
        restaurant_owner_id: uuid.UUID | None = None,
    ) -> ReservationOut:
        """도메인 Reservation + TimeSlot -> 응답 DTO. 시각 칸은 서울 시간으로 바꿔 넣고, can_cancel은 도메인에 물어서 채운다.
        viewer는 보는 사람(역할까지), restaurant_owner_id는 그 식당 주인. 운영자에게 버튼을 보여 줄 때만 필요하다."""
        # DB에서 꺼낸 시각은 UTC라서, 응답에서는 같은 순간을 서울 시계(+09:00)로 다시 읽어 내보낸다
        cancelled_at = reservation.cancelled_at
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
        )
