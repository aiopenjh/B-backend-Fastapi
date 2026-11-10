# [담당 4] 예약 창구 : 예약 생성, 취소(손님·운영자·관리자), 입장 확인 요청을 받아 매니저에게 넘기고 응답 모양으로 돌려줌
from typing import Annotated

from fastapi import APIRouter, Depends, Path, status

from auth.domain.value_object import AuthenticatedUser
from auth.presentation.dependencies import get_authenticated_user, require_admin
from common.schemas import APIResponse
from container import NO_SHOW_GRACE, create_reservation_service
from owner.presentation.dependencies import require_owner
from reservation.application.service import ReservationService
from reservation.domain.reservation import CancelledBy
from reservation.domain.value_object import Actor
from reservation.presentation.schemas import (
    BIGINT_MAX,
    ReservationCancelRequest,
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
        data=ReservationOut.from_domain(reservation, slot, me, now),
        message="예약이 완료되었습니다.",
    )


@router.post(
    "/{reservation_id}/cancel",
    response_model=APIResponse[ReservationOut],
    responses={
        404: {
            "model": APIResponse[None],
            "description": "예약이 없거나 남의 예약 (운영자·관리자 취소는 /owner, /admin 주소)",
        },
        409: {
            "model": APIResponse[None],
            "description": "이미 취소한 예약이거나 슬롯이 이미 시작됨",
        },
    },
    summary="내 예약 취소 (예약자 본인)",
)
async def cancel_reservation(
    reservation_id: Annotated[
        int, Path(ge=1, le=BIGINT_MAX, description="취소할 예약 번호")
    ],
    me: Annotated[AuthenticatedUser, Depends(get_authenticated_user)],
    service: Annotated[ReservationService, Depends(create_reservation_service)],
) -> APIResponse[ReservationOut]:
    now = seoul_now()  # 취소 판단과 응답의 can_cancel이 같은 시각을 쓰도록 한 번만 구함
    # 기본값이 손님 취소(누가 CUSTOMER, 이유 CUSTOMER_REQUEST)라 내 예약만 취소된다
    # 로그인한 사람을 예약 쪽 Actor로 바꿔서 넘긴다 (매니저·도메인은 로그인 모듈을 모른다)
    reservation, slot = await service.cancel(
        user=Actor(me.user_id, me.role), reservation_id=reservation_id, now=now
    )
    return APIResponse.ok(data=ReservationOut.from_domain(reservation, slot, me, now))


# 운영자 창구 : 내 식당 예약 취소(이유 필수, 노쇼 포함)와 입장 확인
owner_router = APIRouter(prefix="/owner/reservations", tags=["운영자 예약"])


@owner_router.post(
    "/{reservation_id}/cancel",
    response_model=APIResponse[ReservationOut],
    responses={
        403: {"model": APIResponse[None], "description": "운영자가 아님"},
        404: {
            "model": APIResponse[None],
            "description": "예약이 없거나 내 식당 예약이 아님",
        },
        409: {
            "model": APIResponse[None],
            "description": "이미 취소됨, 시작 후 일반 취소, 노쇼로 하기엔 이름, 이미 입장 확인됨",
        },
        422: {"model": APIResponse[None], "description": "운영자가 쓸 수 없는 이유"},
    },
    summary="운영자 예약 취소 (전화 요청, 식당 사정, 기타, 노쇼)",
)
async def owner_cancel_reservation(
    reservation_id: Annotated[
        int, Path(ge=1, le=BIGINT_MAX, description="취소할 예약 번호")
    ],
    body: ReservationCancelRequest,
    owner: Annotated[AuthenticatedUser, Depends(require_owner)],
    service: Annotated[ReservationService, Depends(create_reservation_service)],
) -> APIResponse[ReservationOut]:
    now = seoul_now()
    reservation, slot = await service.cancel(
        user=Actor(owner.user_id, owner.role),
        reservation_id=reservation_id,
        now=now,
        by=CancelledBy.OWNER,
        reason=body.reason,
        note=body.note,
    )
    # 매니저가 내 식당인지 이미 확인했으니 식당 주인 = 나
    return APIResponse.ok(
        data=ReservationOut.from_domain(
            reservation,
            slot,
            owner,
            now,
            restaurant_owner_id=owner.user_id,
            no_show_grace=NO_SHOW_GRACE,
        )
    )


@owner_router.post(
    "/{reservation_id}/check-in",
    response_model=APIResponse[ReservationOut],
    responses={
        403: {"model": APIResponse[None], "description": "운영자가 아님"},
        404: {
            "model": APIResponse[None],
            "description": "예약이 없거나 내 식당 예약이 아님",
        },
        409: {
            "model": APIResponse[None],
            "description": "이미 입장 확인됨, 취소된 예약, 입장 확인 시간(시작 30분 전 ~ 끝나기 전)이 아님",
        },
    },
    summary="입장 확인 (손님이 왔음을 기록)",
)
async def owner_check_in(
    reservation_id: Annotated[
        int, Path(ge=1, le=BIGINT_MAX, description="입장 확인할 예약 번호")
    ],
    owner: Annotated[AuthenticatedUser, Depends(require_owner)],
    service: Annotated[ReservationService, Depends(create_reservation_service)],
) -> APIResponse[ReservationOut]:
    now = seoul_now()
    reservation, slot = await service.check_in(
        user=Actor(owner.user_id, owner.role), reservation_id=reservation_id, now=now
    )
    return APIResponse.ok(
        data=ReservationOut.from_domain(
            reservation,
            slot,
            owner,
            now,
            restaurant_owner_id=owner.user_id,
            no_show_grace=NO_SHOW_GRACE,
        )
    )


# 관리자 창구 : 모든 예약 취소 (시각 제한 없음, 메모 필수)
admin_router = APIRouter(prefix="/admin/reservations", tags=["관리자 예약"])


@admin_router.post(
    "/{reservation_id}/cancel",
    response_model=APIResponse[ReservationOut],
    responses={
        403: {"model": APIResponse[None], "description": "관리자가 아님"},
        404: {"model": APIResponse[None], "description": "예약이 없음"},
        409: {"model": APIResponse[None], "description": "이미 취소한 예약"},
        422: {
            "model": APIResponse[None],
            "description": "관리자가 쓸 수 없는 이유, 메모 없음",
        },
    },
    summary="관리자 예약 취소 (시스템 오류, 기타 / 메모 필수)",
)
async def admin_cancel_reservation(
    reservation_id: Annotated[
        int, Path(ge=1, le=BIGINT_MAX, description="취소할 예약 번호")
    ],
    body: ReservationCancelRequest,
    admin: Annotated[AuthenticatedUser, Depends(require_admin)],
    service: Annotated[ReservationService, Depends(create_reservation_service)],
) -> APIResponse[ReservationOut]:
    now = seoul_now()
    reservation, slot = await service.cancel(
        user=Actor(admin.user_id, admin.role),
        reservation_id=reservation_id,
        now=now,
        by=CancelledBy.ADMIN,
        reason=body.reason,
        note=body.note,
    )
    return APIResponse.ok(
        data=ReservationOut.from_domain(reservation, slot, admin, now)
    )
