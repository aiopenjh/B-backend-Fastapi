# [담당 5] Jinja2 화면 창구: /ui 주소로 HTML 돌려주기
"""기존 조회 흐름을 위한 HTML 화면.

손님용 식당 목록·상세는 실제 데이터와 연결됨 (로그인 필요 없음).
운영자 화면은 화면용 로그인(쿠키)이 붙은 뒤 연결한다.
"""

from datetime import date as Date, datetime, timedelta
from pathlib import Path
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, FastAPI, Path as PathParam, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BeforeValidator
from common.pagination import PageParams
from common.schemas import SEOUL
from container import create_restaurant_service  # 담당 2: 식당 매니저 공장
from restaurant.application.service import RestaurantService  # 담당 2: 식당 매니저
from restaurant.domain.exceptions import RestaurantNotFoundError  # 담당 2: 없는 식당
from restaurant.presentation.routers.v1.router import BIGINT_MAX  # 담당 2: 식당 번호 상한
from slot.application.service import SlotService  # 담당 3: 빈자리 매니저
from slot.domain.day_range import seoul_now  # 담당 3: 서울 지금 시각
from web_data import OwnerUIQueries, PageResult, get_owner_ui_queries, get_slot_service

SRC_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(SRC_DIR / "templates"))
router = APIRouter(prefix="/ui", include_in_schema=False)


def seoul_datetime(value):
    if isinstance(value, str):
        value = datetime.fromisoformat(value)
    if not isinstance(value, datetime):
        return str(value)
    if value.tzinfo is None:
        return value.isoformat(sep=" ")
    return value.astimezone(SEOUL).strftime("%Y.%m.%d  %H:%M")


def seoul_time(value: datetime) -> str:
    """빈자리 시간대용: 서울 시각 '18:00'"""
    return value.astimezone(SEOUL).strftime("%H:%M")


templates.env.filters["seoul_datetime"] = seoul_datetime
templates.env.filters["seoul_time"] = seoul_time
OwnerQueries = Annotated[OwnerUIQueries | None, Depends(get_owner_ui_queries)]
Restaurants = Annotated[RestaurantService, Depends(create_restaurant_service)]
Slots = Annotated[SlotService, Depends(get_slot_service)]
PageNumber = Annotated[int, Query(ge=1)]
PageSize = Annotated[int, Query(ge=1, le=100)]
# 빈 칸으로 보낸 폼 값("")은 '안 고름'(None)으로 본다
Blank = BeforeValidator(lambda value: value or None)


@router.get("", response_class=HTMLResponse, name="ui_login")
async def login_page(request: Request):
    return templates.TemplateResponse(
        request=request, name="login.html", context={"active_page": "login"}
    )


@router.get("/owner/restaurants", response_class=HTMLResponse, name="ui_restaurants")
async def restaurants_page(
    request: Request, source: OwnerQueries, page: PageNumber = 1, page_size: PageSize = 20
):
    result = await source.restaurants(page, page_size) if source else None
    # None은 미연결이다. 실제 조회 결과가 없을 때만 []를 전달한다.
    return templates.TemplateResponse(
        request=request,
        name="owner/restaurants.html",
        context={
            "active_page": "restaurants", "restaurants": result.items if result else None,
            "total": result.total if result else None, "result": result,
            "page_size": page_size,
        },
    )


@router.get(
    "/owner/restaurants/{restaurant_id}/reservations",
    response_class=HTMLResponse,
    name="ui_reservations",
)
async def reservations_page(
    request: Request,
    restaurant_id: Annotated[int, PathParam(gt=0)],
    source: OwnerQueries,
    date: Annotated[Date | None, BeforeValidator(lambda value: value or None)] = None,
    page: PageNumber = 1,
    page_size: PageSize = 20,
):
    result = await source.reservations(restaurant_id, date, page, page_size) if source else None
    # 실제 데이터를 넣기 전에 require_owner와 서비스의 소유권 검사를 연결한다.
    return templates.TemplateResponse(
        request=request,
        name="owner/reservations.html",
        context={
            "active_page": "reservations",
            "restaurant_id": restaurant_id,
            "selected_date": date.isoformat() if date else "",
            "reservations": result.items if result else None,
            "total": result.total if result else None,
            "result": result,
            "page_size": page_size,
        },
    )


# 담당 5: 손님용 식당 목록 화면 (로그인 필요 없음, 담당 2 식당 매니저 #32 재사용)
@router.get("/restaurants", response_class=HTMLResponse, name="ui_browse")
async def browse_page(
    request: Request,
    service: Restaurants,
    q: Annotated[str | None, Blank] = None,
    cuisine: Annotated[str | None, Blank] = None,
    sort: Literal["id", "name"] = "id",
    page: PageNumber = 1,
    page_size: PageSize = 12,
):
    items, total = await service.list_restaurants(
        q, cuisine, sort, PageParams(page=page, page_size=page_size)
    )
    return templates.TemplateResponse(
        request=request,
        name="restaurants/list.html",
        context={
            "active_page": "browse", "restaurants": items, "total": total,
            "result": PageResult(items, total, page, page_size),
            "q": q or "", "cuisine": cuisine or "", "sort": sort,
        },
    )


# 담당 5: 손님용 식당 상세 화면 (메뉴 + 날짜·인원별 빈자리, 담당 3 빈자리 매니저 #33 재사용)
@router.get("/restaurants/{restaurant_id}", response_class=HTMLResponse, name="ui_restaurant")
async def restaurant_page(
    request: Request,
    restaurant_id: Annotated[int, PathParam(ge=1, le=BIGINT_MAX)],
    service: Restaurants,
    slots: Slots,
    date: Annotated[Date | None, Blank] = None,
    party_size: Annotated[int, Query(ge=1, le=20)] = 2,
):
    day = date or (seoul_now() + timedelta(days=1)).date()  # 안 고르면 내일(서울)
    try:
        restaurant = await service.get_restaurant(restaurant_id)
    except RestaurantNotFoundError:
        # 화면은 JSON 실패 봉투 대신 404 안내 화면을 보여 준다
        return templates.TemplateResponse(
            request=request,
            name="restaurants/detail.html",
            context={"active_page": "browse", "restaurant": None},
            status_code=404,
        )
    availability = await slots.get_availability(restaurant_id, day, party_size)
    return templates.TemplateResponse(
        request=request,
        name="restaurants/detail.html",
        context={
            "active_page": "browse", "restaurant": restaurant,
            "availability": availability, "selected_date": day.isoformat(),
            "party_size": party_size,
        },
    )


def register_web(app: FastAPI) -> None:
    """HTML 라우터와 정적 파일을 기존 앱에 등록한다."""
    app.mount("/static", StaticFiles(directory=str(SRC_DIR / "static")), name="static")
    app.include_router(router)
