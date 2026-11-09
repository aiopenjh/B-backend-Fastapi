# [담당 4] 예약 응답 모양 : API로 내보내는 예약 정보(모양)
import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, Field

from common.schemas import SEOUL
from reservation.domain.reservation import Reservation, ReservationStatus
from slot.domain.time_slot import TimeSlot


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
    cancelled_at: Annotated[datetime | None, Field(description="취소한 시각 (취소 전에는 null)")]
    can_cancel: Annotated[
        bool,
        Field(description="취소 가능 여부. 요청한 사람이 예약자이고, 확정 상태이고, 슬롯 시작 전이면 true"),
    ]

    @classmethod
    def from_domain(
        cls,
        reservation: Reservation,
        slot: TimeSlot,
        viewer_id: uuid.UUID,
        now: datetime,
    ) -> ReservationOut:
        """도메인 Reservation + TimeSlot -> 응답 DTO. 시각 칸은 서울 시간으로 바꿔 넣고, can_cancel은 도메인에 물어서 채운다."""
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
                user_id=viewer_id,
                slot_starts_at=slot.starts_at,
                now=now,
            ),
        )
    