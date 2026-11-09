# [담당 5] 운영자 API 창구: 내 식당 목록, 식당 예약 목록, 예약 CSV 내려받기
import csv
import io

from datetime import date
from fastapi import APIRouter, Depends, BackgroundTasks

from fastapi.responses import StreamingResponse
from common.logger import get_logger # 담당1 : 로그
from common.schemas import APIResponse # 담당1 : 응답봉투
from common.pagination import Page, PageParams, page_params # 담당 2: 목록 모양페이지
from owner.presentation.dependencies import require_owner # 만든 오너 문
from owner.application.service import OwnerService # 담당 5 : 매니저
from restaurant.presentation.schemas import RestaurantOut # 담당 2 : 식당 응답 모양
from reservation.presentation.schemas import ReservationOut # 담당 4 : 민지님
from auth.domain.value_object import AuthenticatedUser # 담당 1 : 회원
from container import create_owner_service # 담당 5: 매니저 공장
from slot.domain.day_range import SEOUL, seoul_now # 담당3 : 서울시간대, 지금 시각



logger = get_logger(__name__)

def log_export_csv(owner_id, restaurant_id, count):
    logger.info(f"CSV 운영자 {owner_id} 식당 {restaurant_id} 예약 {count}건 다운로드")


# 담당 5: CSV를 한 줄씩 만들어 보내기 (쓰고 → 보내고 → 지우고)
async def make_csv_rows(items):
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    yield "\ufeff"

    writer.writerow(["예약번호", "시작", "끝", "인원", "상태", "연락처"])
    yield buffer.getvalue()
    buffer.seek(0)
    buffer.truncate(0)
    # 예약 한 건 = 한 줄 (r: 예약, s: 슬롯)
    for r, s in items:
        writer.writerow([
            r.id,
            s.starts_at.astimezone(SEOUL).strftime("%Y-%m-%d %H:%M"),
            s.ends_at.astimezone(SEOUL).strftime("%Y-%m-%d %H:%M"),
            r.party_size,
            r.status,
            r.contact_phone
        ])
        yield buffer.getvalue()
        buffer.seek(0)
        buffer.truncate(0)

router = APIRouter(prefix="/owner", tags=["운영자"], dependencies=[Depends(require_owner)])


@router.get("/restaurants", response_model=APIResponse[Page[RestaurantOut]], summary="내가 운영하는 식당 목록")
async def list_my_restaurants(
    page: PageParams = Depends(page_params),
    owner: AuthenticatedUser = Depends(require_owner),
    service: OwnerService = Depends(create_owner_service),
) -> APIResponse[Page[RestaurantOut]]:
    items, total = await service.list_my_restaurants(owner, page)
    return APIResponse.ok(data=Page(
        items=[RestaurantOut.model_validate(r) for r in items],
        page=page.page,
        page_size=page.page_size,
        total=total,
    ))


@router.get("/restaurants/{restaurant_id}/reservations", response_model=APIResponse[Page[ReservationOut]], summary="식당 예약 목록")
async def list_restaurant_reservations(
    restaurant_id: int,
    date: date | None = None,
    page: PageParams = Depends(page_params),
    owner: AuthenticatedUser = Depends(require_owner),
    service: OwnerService = Depends(create_owner_service),
) -> APIResponse[Page[ReservationOut]]:
    items, total = await service.list_restaurant_reservations(owner, restaurant_id, date, page)
    now = seoul_now()
    return APIResponse.ok(data=Page(
        # 보는 사람 = 운영자 (운영자는 손님 예약을 취소할 수 없으니 can_cancel은 False)
        items=[ReservationOut.from_domain(r, s, owner.user_id, now) for r, s in items],
        page=page.page,
        page_size=page.page_size,
        total=total,
    ))

@router.get("/restaurants/{restaurant_id}/reservations/export/csv", summary="식당 예약 CSV 내려받기")
async def export_restaurant_reservations(
    restaurant_id: int,
    background_tasks: BackgroundTasks,          # 응답 뒤에 할 일 목록 (FastAPI가 넣어 줌)
    date: date | None = None,
    owner: AuthenticatedUser = Depends(require_owner),
    service: OwnerService = Depends(create_owner_service),
):
    # 1. 매니저한테 예약 전부 받기 (404·403은 매니저가 판단)
    items = await service.export_restaurant_reservations(owner, restaurant_id, date)

    # 2. 응답 뒤에 기록 남기기 예약
    background_tasks.add_task(log_export_csv, owner.user_id, restaurant_id, len(items))

    # 3. CSV를 흘려보내기
    return StreamingResponse(
        make_csv_rows(items),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="reservations_{restaurant_id}.csv"'},
    )