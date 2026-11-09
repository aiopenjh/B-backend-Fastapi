# [담당 4] 예약 창구 : 예약 생성, 취소 요청을 받아 매니저에게 넘기고 응답 모양으로 돌려줌
from typing import Annotated

from fastapi import APIRouter, Depends, Path

from auth.domain.value_object import AuthenticatedUser
from auth.presentation.dependencies import get_authenticated_user
from common.schemas import APIResponse
from container import create_reservation_service
from reservation.application.service import ReservationService
from reservation.presentation.schemas import ReservationOut
from slot.domain.day_range import seoul_now

router = APIRouter(tags=["예약"])


@router.post(
    "/reservations/{reservation_id}/cancel",
    response_model=APIResponse[ReservationOut],
    responses={
        404: {"model": APIResponse[None], "description": "예약이 없거나 남의 예약"},
        409: {
            "model": APIResponse[None],
            "description": "이미 취소한 예약이거나 슬롯이 이미 시작됨",
        },
    },
    summary="예약 취소",
)
async def cancel_reservation(
    reservation_id: Annotated[int, Path(gt=0, description="취소할 예약 번호")],
    me: Annotated[AuthenticatedUser, Depends(get_authenticated_user)],
    service: Annotated[ReservationService, Depends(create_reservation_service)],
) -> APIResponse[ReservationOut]:
    now = seoul_now()  # 취소 판단과 응답의 can_cancel이 같은 시각을 쓰도록 한 번만 구함
    reservation, slot = await service.cancel(
        user_id=me.user_id, reservation_id=reservation_id, now=now
    )
    return APIResponse.ok(
        data=ReservationOut.from_domain(reservation, slot, me.user_id, now)
    )
