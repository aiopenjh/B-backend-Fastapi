# [담당 4] 예약 창구 : 예약 생성, 취소 요청을 받아 매니저에게 넘기고 응답 모양으로 돌려줌
from typing import Annotated

from fastapi import APIRouter, Depends, Path, status

from auth.domain.value_object import AuthenticatedUser
from auth.presentation.dependencies import get_authenticated_user
from common.schemas import APIResponse
from container import create_reservation_service
from reservation.application.service import ReservationService
from reservation.presentation.schemas import (
    BIGINT_MAX,
    ReservationCreate,
    ReservationOut,
)
from slot.domain.day_range import seoul_now

router = APIRouter(prefix="/reservations", tags=["예약"])


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=APIResponse[ReservationOut],
    responses={
        404: {"model": APIResponse[None], "description": "없는 슬롯"},
        409: {
            "model": APIResponse[None],
            "description": "슬롯이 이미 시작됨, 한 팀 최대 인원 초과, 자리 부족, 이미 예약한 시간대",
        },
    },
    summary="예약 생성",
)
async def create_reservation(
    body: ReservationCreate,
    me: Annotated[AuthenticatedUser, Depends(get_authenticated_user)],
    service: Annotated[ReservationService, Depends(create_reservation_service)],
) -> APIResponse[ReservationOut]:
    now = seoul_now()  # 예약 판단과 응답의 can_cancel이 같은 시각을 쓰도록 한 번만 구함
    reservation, slot = await service.create(
        user_id=me.user_id,
        slot_id=body.slot_id,
        party_size=body.party_size,
        contact_phone=body.contact_phone,
        now=now,
    )
    return APIResponse.ok(
        data=ReservationOut.from_domain(reservation, slot, me.user_id, now),
        message="예약이 완료되었습니다.",
    )


@router.post(
    "/{reservation_id}/cancel",
    response_model=APIResponse[ReservationOut],
    responses={
        404: {
            "model": APIResponse[None],
            "description": "예약이 없거나, 취소할 수 없는 사람의 요청 (남의 예약, 다른 식당 예약)",
        },
        409: {
            "model": APIResponse[None],
            "description": "이미 취소한 예약이거나 슬롯이 이미 시작됨",
        },
    },
    summary="예약 취소 (예약자 본인, 그 식당 운영자, 관리자)",
)
async def cancel_reservation(
    reservation_id: Annotated[
        int, Path(ge=1, le=BIGINT_MAX, description="취소할 예약 번호")
    ],
    me: Annotated[AuthenticatedUser, Depends(get_authenticated_user)],
    service: Annotated[ReservationService, Depends(create_reservation_service)],
) -> APIResponse[ReservationOut]:
    now = seoul_now()  # 취소 판단과 응답의 can_cancel이 같은 시각을 쓰도록 한 번만 구함
    reservation, slot = await service.cancel(
        user=me, reservation_id=reservation_id, now=now
    )  # 역할(손님, 운영자, 관리자)까지 봐야 해서 로그인한 사람 전체를 넘김
    return APIResponse.ok(
        data=ReservationOut.from_domain(reservation, slot, me.user_id, now)
    )
