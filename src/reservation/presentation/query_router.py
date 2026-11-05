# [담당 5] 예약 조회 창구: 손님 요청 받기
from fastapi import APIRouter, Depends

from auth.domain.value_object import AuthenticatedUser  # 담당 1: 로그인한 사람
from auth.presentation.dependencies import get_authenticated_user  # 담당 1: 로그인 문지기
from common.pagination import Page, PageParams, page_params  # 담당 2: 페이지 (아직 없음)
from common.schemas import APIResponse  # 담당 1: 응답 봉투
from container import create_reservation_query_service  # 담당 5: 매니저 공장 (곧 만듦)
from reservation.application.query_service import ReservationQueryService  # 담당 5: 매니저
from reservation.domain.reservation import ReservationStatus  # 담당 4: 예약 상태
from reservation.presentation.schemas import ReservationOut  # 담당 4: 예약 응답 모양

router = APIRouter(tags=["내 예약"])


@router.get("/users/me/reservations", response_model=APIResponse[Page[ReservationOut]], summary="내 예약 목록")
async def list_my_reservations(
    status: ReservationStatus | None = None,
    page: PageParams = Depends(page_params),
    me: AuthenticatedUser = Depends(get_authenticated_user),
    service: ReservationQueryService = Depends(create_reservation_query_service),
) -> APIResponse[Page[ReservationOut]]:
    # 매니저에게 "내 예약 꺼내 와" 시키기
    items, total = await service.list_my_reservations(me, status, page)
    return APIResponse.ok(data=Page(
        items=[ReservationOut.from_domain(r, s) for r, s in items],  # 담당 4: 아직 없음
        page=page.page,
        page_size=page.page_size,
        total=total,
    ))


# 5단계: 예약 상세
@router.get("/reservations/{reservation_id}", response_model=APIResponse[ReservationOut], summary="예약 상세")
async def get_reservation(
    reservation_id: int,
    me: AuthenticatedUser = Depends(get_authenticated_user),
    service: ReservationQueryService = Depends(create_reservation_query_service),
) -> APIResponse[ReservationOut]:
    # 매니저에게 "이 예약 보여 줘도 되는지 보고 꺼내 와" 시키기
    reservation, slot = await service.get_reservation(me, reservation_id)
    return APIResponse.ok(data=ReservationOut.from_domain(reservation, slot))
