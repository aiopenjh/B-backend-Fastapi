# [담당3-영민] 예약 가능 시간대 조회 창구
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query

from common.schemas import SEOUL, APIResponse
from container import create_slot_service
from slot.application.service import SlotService
from slot.presentation.schemas import AvailabilityOut, SlotOut

# BIGINT 최댓값. 이보다 큰 id는 DB 오류(500) 대신 422로 막음 (식당 라우터와 같은 상한)
BIGINT_MAX = 9223372036854775807

router = APIRouter(prefix="/restaurants", tags=["slot"])


@router.get(
    "/{restaurant_id}/availability",
    response_model=APIResponse[AvailabilityOut],
    summary="예약 가능 시간대 조회",
)
async def get_availability(
    restaurant_id: Annotated[int, Path(ge=1, le=BIGINT_MAX, description="식당 id")],
    date_: Annotated[
        date,
        Query(alias="date", description="YYYY-MM-DD, Asia/Seoul 기준 하루"),
    ],
    party_size: Annotated[int, Query(ge=1, description="예약 인원수")],
    service: Annotated[SlotService, Depends(create_slot_service)],
) -> APIResponse[AvailabilityOut]:
    items = await service.get_availability(restaurant_id, date_, party_size)

    data = AvailabilityOut(
        restaurant_id=restaurant_id,
        date=date_,
        slots=[
            SlotOut(
                id=a.slot.id,
                # DB에서 꺼낸 시각은 UTC라서, 같은 순간을 서울 시계(+09:00)로 다시 읽어 내보냄
                starts_at=a.slot.starts_at.astimezone(SEOUL),
                ends_at=a.slot.ends_at.astimezone(SEOUL),
                remaining=a.slot.remaining,
                max_party_size=a.slot.max_party_size,
                available=a.available,
            )
            for a in items
        ],
    )

    return APIResponse.ok(data, message="예약 가능 시간대를 조회했습니다.")
