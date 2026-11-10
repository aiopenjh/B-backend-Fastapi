# [담당 5] Jinja2 화면 창구: /ui 주소로 HTML 돌려주기
"""기존 조회 흐름을 위한 HTML 화면.

손님용 식당 목록·상세는 로그인 없이 실제 데이터를 보여 준다.
운영자 화면은 화면 로그인(JWT를 쿠키에 담기, web_auth.py) 뒤에 실제 데이터를 보여 준다.
"""

import secrets
import uuid
from datetime import date as Date
from datetime import datetime, timedelta
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, FastAPI, Form, Query, Request
from fastapi import Path as PathParam
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BeforeValidator

from admin.application.service import AdminService  # 담당 5: 관리자 매니저
from auth.application.service import AuthService  # 담당 1: 로그인 매니저
from browse.application.service import BrowseService  # 담당 5: 손님 둘러보기 매니저
from common.errors import AppError  # 공통 오류 (404·403 안내 화면으로 바꿈)
from common.pagination import PageParams
from common.schemas import SEOUL
from container import (
    create_admin_service,  # 담당 5: 관리자 매니저 공장
    create_auth_service,  # 담당 1: 로그인 매니저 공장
    create_browse_service,  # 담당 5: 손님 둘러보기 매니저 공장
    create_reservation_query_service,  # 담당 5: 예약 조회 매니저 공장
    create_reservation_service,  # 담당 4: 예약 매니저 공장 (#46)
    create_restaurant_service,  # 담당 2: 식당 매니저 공장
    create_slot_service,  # 담당 3: 빈자리 매니저 공장 (#44)
)
from reservation.application.query_service import (
    ReservationQueryService,  # 담당 5: 예약 조회 매니저
)
from reservation.application.service import ReservationService  # 담당 4: 예약 매니저
from restaurant.application.service import RestaurantService  # 담당 2: 식당 매니저
from restaurant.domain.exceptions import RestaurantNotFoundError  # 담당 2: 없는 식당
from restaurant.presentation.routers.v1.router import (
    BIGINT_MAX,  # 담당 2: 식당 번호 상한
)
from slot.application.service import SlotService  # 담당 3: 빈자리 매니저
from slot.domain.day_range import seoul_now  # 담당 3: 서울 지금 시각
from web_auth import (  # 담당 5: 화면 로그인
    COOKIE_NAME,
    COOKIE_PATH,
    get_ui_user,
    home_url,
    safe_next,
    to_login,
)
from web_data import (
    OwnerUIQueries,
    PageResult,
    get_owner_ui_queries,
)

SRC_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(SRC_DIR / "templates"))
# 모든 화면에서 쿠키 로그인 상태를 먼저 읽어 둔다 (사이드바가 씀). 로그인 안 해도 화면은 열림
router = APIRouter(prefix="/ui", include_in_schema=False, dependencies=[Depends(get_ui_user)])


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
Slots = Annotated[SlotService, Depends(create_slot_service)]
PageNumber = Annotated[int, Query(ge=1)]
PageSize = Annotated[int, Query(ge=1, le=100)]
# 빈 칸으로 보낸 폼 값("")은 '안 고름'(None)으로 본다
Blank = BeforeValidator(lambda value: value or None)
Auth = Annotated[AuthService, Depends(create_auth_service)]
Admin = Annotated[AdminService, Depends(create_admin_service)]
Browse = Annotated[BrowseService, Depends(create_browse_service)]
Booking = Annotated[ReservationService, Depends(create_reservation_service)]
MyReservations = Annotated[ReservationQueryService, Depends(create_reservation_query_service)]

# 예약하기 실패를 손님이 읽는 문구로 (오류 코드 → 문구)
BOOKING_ERRORS = {
    "SLOT_SOLD_OUT": "방금 자리가 찼어요. 다른 시간을 골라 주세요.",
    "PARTY_SIZE_EXCEEDED": "이 시간은 한 번에 예약할 수 있는 인원을 넘었어요.",
    "SLOT_ALREADY_STARTED": "이미 시작한 시간이에요. 다른 시간을 골라 주세요.",
    "DUPLICATE_RESERVATION": "이미 예약한 시간이에요.",
    "NOT_THIS_RESTAURANT": "선택한 시간을 찾을 수 없어요. 다시 골라 주세요.",
}


def message_page(request: Request, status_code: int, title: str, text: str) -> HTMLResponse:
    """오류를 JSON 대신 안내 화면으로 (403·404). 버튼은 그 사람의 첫 화면으로"""
    user = request.state.ui_user
    home = home_url(request, user) if user else str(request.url_for("ui_browse"))
    return templates.TemplateResponse(
        request=request, name="message.html", status_code=status_code,
        context={"active_page": "", "title": title, "text": text, "home": home},
    )


def staff_redirect(request: Request) -> RedirectResponse | None:
    """손님 공간 문: 운영자는 손님 화면 대신 자기 공간(운영 식당)으로 돌려보낸다. 관리자는 손님 화면도 볼 수 있음"""
    user = request.state.ui_user
    if user is not None and user.is_owner():
        return RedirectResponse(home_url(request, user), status_code=303)
    return None


def deny(request: Request) -> RedirectResponse | HTMLResponse:
    """운영자 화면 문: 로그인 안 했으면 로그인 화면으로, 로그인했는데 운영자가 아니면 403 안내"""
    user = request.state.ui_user
    if user is None:
        return to_login(request)
    if user.is_admin():
        # 관리자는 모든 운영자의 식당을 관리자 화면에서 본다 (운영자 화면은 "로그인한 운영자 본인" 것만 보여 줌)
        return RedirectResponse(request.url_for("ui_admin_owners"), status_code=303)
    return message_page(request, 403, "운영자만 볼 수 있어요", "운영자 계정으로 로그인해 주세요.")


def deny_admin(request: Request) -> RedirectResponse | HTMLResponse | None:
    """관리자 화면 문: 로그인 안 했으면 로그인 화면, 관리자가 아니면 403 안내, 관리자면 None(통과)"""
    user = request.state.ui_user
    if user is None:
        return to_login(request)
    if not user.is_admin():
        return message_page(request, 403, "관리자만 볼 수 있어요", "관리자 계정으로 로그인해 주세요.")
    return None


@router.get("", response_class=HTMLResponse, name="ui_login")
async def login_page(request: Request, next: str | None = None):
    return templates.TemplateResponse(
        request=request, name="login.html",
        context={"active_page": "login", "next": safe_next(next) or "", "email": "", "error": None},
    )


# 담당 5: 화면 로그인 — 담당 1 login으로 JWT를 받아 HttpOnly 쿠키에 담는다
@router.post("/login", name="ui_login_submit")
async def login_submit(
    request: Request,
    auth: Auth,
    username: Annotated[str, Form()] = "",
    password: Annotated[str, Form()] = "",
    next: Annotated[str, Form()] = "",
):
    try:
        issued = await auth.login(email=username, password=password)
        user = await auth.authenticate(token=issued.access_token)
    except AppError:
        # 이메일·비밀번호가 틀리면 같은 화면에 문구를 띄움 (어느 쪽이 틀렸는지는 알려 주지 않음)
        return templates.TemplateResponse(
            request=request, name="login.html", status_code=401,
            context={"active_page": "login", "next": safe_next(next) or "", "email": username,
                     "error": "이메일 또는 비밀번호가 올바르지 않습니다."},
        )
    response = RedirectResponse(safe_next(next) or home_url(request, user), status_code=303)
    response.set_cookie(
        COOKIE_NAME, issued.access_token, max_age=issued.expires_in,
        httponly=True, samesite="lax", path=COOKIE_PATH,  # 자바스크립트로 못 읽고, 화면 주소에만 보냄
        secure=request.url.scheme == "https",  # https로 열렸으면 https에서만 쿠키를 보냄 (로컬 http는 그대로)
    )
    return response


# 담당 5: 화면 로그아웃 — 담당 1 logout(#45)으로 토큰을 막고, 쿠키를 지운다
@router.post("/logout", name="ui_logout")
async def logout_submit(request: Request, auth: Auth):
    token = request.cookies.get(COOKIE_NAME)
    if token:
        try:
            await auth.logout(token=token)  # 차단 명단에 올림 → 복사해 둔 같은 토큰도 이제 못 씀
        except AppError:
            pass  # 이미 만료·로그아웃된 토큰이면 막을 것이 없으니 쿠키만 지운다
    response = RedirectResponse(request.url_for("ui_login"), status_code=303)
    response.delete_cookie(COOKIE_NAME, path=COOKIE_PATH)
    return response


@router.get("/owner/restaurants", response_class=HTMLResponse, name="ui_restaurants")
async def restaurants_page(
    request: Request, source: OwnerQueries, page: PageNumber = 1, page_size: PageSize = 20
):
    if source is None:
        return deny(request)
    result = await source.restaurants(page, page_size)
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
    restaurant_id: Annotated[int, PathParam(gt=0, le=BIGINT_MAX)],
    source: OwnerQueries,
    date: Annotated[Date | None, BeforeValidator(lambda value: value or None)] = None,
    page: PageNumber = 1,
    page_size: PageSize = 20,
):
    if source is None:
        return deny(request)
    try:
        # 매니저가 없는 식당 404, 남의 식당 403을 판단한다 (운영자 API와 같은 규칙)
        result = await source.reservations(restaurant_id, date, page, page_size)
    except AppError as error:
        return message_page(request, error.error_code.status, "예약을 볼 수 없어요", error.message)
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


# 담당 5: 손님용 식당 목록 화면 (로그인 필요 없음). 식당 이름·음식 종류·지역(시·도 → 구)으로 찾고 10개씩
@router.get("/restaurants", response_class=HTMLResponse, name="ui_browse")
async def browse_page(
    request: Request,
    browse: Browse,
    q: Annotated[str | None, Blank] = None,
    cuisine: Annotated[str | None, Blank] = None,
    region: Annotated[str | None, Blank] = None,
    district: Annotated[str | None, Blank] = None,
    page: PageNumber = 1,
    page_size: PageSize = 10,
):
    if moved := staff_redirect(request):
        return moved
    # 열 때마다(새로고침 포함) 새로 섞음
    seed = secrets.token_hex(4)
    if not region:
        district = None
    districts = await browse.list_districts(region) if region else []
    items, total = await browse.list_restaurants(
        region, district, q, cuisine, seed, PageParams(page=page, page_size=page_size)
    )
    return templates.TemplateResponse(
        request=request,
        name="restaurants/list.html",
        context={
            "active_page": "browse", "restaurants": items,
            "result": PageResult(items, total, page, page_size),
            "cuisines": await browse.list_cuisines(), "provinces": browse.list_provinces(),
            "districts": districts,
            "q": q or "", "cuisine": cuisine or "", "region": region or "", "district": district or "",
        },
    )


# 담당 5: 손님용 식당 상세 화면 (메뉴 + 날짜·인원별 시간 골라 예약하기, 담당 3 빈자리 매니저 재사용)
@router.get("/restaurants/{restaurant_id}", response_class=HTMLResponse, name="ui_restaurant")
async def restaurant_page(
    request: Request,
    restaurant_id: Annotated[int, PathParam(ge=1, le=BIGINT_MAX)],
    service: Restaurants,
    slots: Slots,
    browse: Browse,
    my_reservations: MyReservations,
    date: Annotated[Date | None, Blank] = None,
    party_size: Annotated[int, Query(ge=1, le=20)] = 2,
    slot_id: Annotated[int | None, Blank] = None,
    reserved: Annotated[int | None, Blank] = None,
    fail: Annotated[str | None, Blank] = None,
):
    if moved := staff_redirect(request):
        return moved
    now = seoul_now()
    day = date or (now + timedelta(days=1)).date()  # 안 고르면 내일(서울)
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
    # 고를 수 있는 시간이 하나도 없으면 가장 가까운 열린 날짜를 알려 줌
    next_open = None
    if not any(item.available for item in availability):
        next_open = await browse.next_open_day(restaurant_id, now)
    # 방금 예약했으면 내 예약을 꺼내 완료 안내에 씀 (내 것이 아니면 보여 주지 않음)
    done = None
    user = request.state.ui_user
    if reserved and user is not None:
        try:
            done = await my_reservations.get_reservation(user, reserved)
        except AppError:
            done = None
    return templates.TemplateResponse(
        request=request,
        name="restaurants/detail.html",
        context={
            "active_page": "browse", "restaurant": restaurant,
            "availability": availability, "selected_date": day.isoformat(),
            "party_size": party_size, "slot_id": slot_id, "now": now, "next_open": next_open,
            "done": done, "fail": BOOKING_ERRORS.get(fail, "예약하지 못했어요. 다시 골라 주세요.") if fail else None,
            "can_book": user is None or user.is_customer(),
        },
    )


# 담당 5: 화면 예약하기 — 담당 4 예약 매니저(create)를 그대로 부름 (자리 잠금·중복 막기·한 번에 저장)
@router.post("/restaurants/{restaurant_id}/reserve", name="ui_reserve")
async def reserve_submit(
    request: Request,
    restaurant_id: Annotated[int, PathParam(ge=1, le=BIGINT_MAX)],
    slots: Slots,
    booking: Booking,
    slot_id: Annotated[int, Form()],
    party_size: Annotated[int, Form(ge=1, le=20)],
    date: Annotated[Date, Form()],
):
    back = request.url_for("ui_restaurant", restaurant_id=restaurant_id).include_query_params(
        date=date.isoformat(), party_size=party_size
    )
    user = request.state.ui_user
    if user is None:
        # 로그인하면 같은 날짜·인원·시간으로 돌아오게
        chosen = back.include_query_params(slot_id=slot_id)
        here = f"{chosen.path}?{chosen.query}"
        return RedirectResponse(request.url_for("ui_login").include_query_params(next=here), status_code=303)
    if not user.is_customer():
        return message_page(request, 403, "손님 계정으로 예약할 수 있어요", "운영자·관리자 계정으로는 예약하지 않아요.")
    # 이 식당·이 날짜의 시간대인지 먼저 확인 (다른 식당 시간대 번호로 예약하지 못하게)
    available = await slots.get_availability(restaurant_id, date, party_size)
    if slot_id not in {item.slot.id for item in available}:
        return RedirectResponse(back.include_query_params(fail="NOT_THIS_RESTAURANT"), status_code=303)
    try:
        reservation, _ = await booking.create(user.user_id, slot_id, party_size, None, seoul_now())
    except AppError as error:
        return RedirectResponse(back.include_query_params(fail=error.error_code.name, slot_id=slot_id), status_code=303)
    return RedirectResponse(back.include_query_params(reserved=reservation.id), status_code=303)


# 담당 5: 관리자 화면 ① 운영자 목록 + 식당 수
@router.get("/admin/owners", response_class=HTMLResponse, name="ui_admin_owners")
async def admin_owners_page(request: Request, service: Admin, page: PageNumber = 1, page_size: PageSize = 20):
    if denied := deny_admin(request):
        return denied
    rows, total = await service.list_owners(PageParams(page=page, page_size=page_size))
    return templates.TemplateResponse(
        request=request, name="admin/owners.html",
        context={"active_page": "admin", "owners": rows, "total": total,
                 "result": PageResult(rows, total, page, page_size)},
    )


# 담당 5: 관리자 화면 ② 운영자 한 명의 식당 표
@router.get("/admin/owners/{owner_id}/restaurants", response_class=HTMLResponse, name="ui_admin_owner_restaurants")
async def admin_owner_restaurants_page(
    request: Request, owner_id: uuid.UUID, service: Admin, page: PageNumber = 1, page_size: PageSize = 20
):
    if denied := deny_admin(request):
        return denied
    try:
        owner, items, total = await service.list_owner_restaurants(owner_id, PageParams(page=page, page_size=page_size))
    except AppError as error:
        return message_page(request, error.error_code.status, "운영자를 찾을 수 없어요", error.message)
    return templates.TemplateResponse(
        request=request, name="admin/restaurants.html",
        context={"active_page": "admin", "owner": owner, "restaurants": items, "total": total,
                 "result": PageResult(items, total, page, page_size)},
    )


# 담당 5: 관리자 화면 ③ 식당 하나의 날짜별 예약 + 예약자
@router.get("/admin/restaurants/{restaurant_id}/reservations", response_class=HTMLResponse, name="ui_admin_reservations")
async def admin_reservations_page(
    request: Request,
    restaurant_id: Annotated[int, PathParam(gt=0, le=BIGINT_MAX)],
    service: Admin,
    date: Annotated[Date | None, Blank] = None,
    page: PageNumber = 1,
    page_size: PageSize = 20,
):
    if denied := deny_admin(request):
        return denied
    try:
        restaurant, rows, total = await service.list_restaurant_reservations(
            restaurant_id, date, PageParams(page=page, page_size=page_size)
        )
    except AppError as error:
        return message_page(request, error.error_code.status, "식당을 찾을 수 없어요", error.message)
    return templates.TemplateResponse(
        request=request, name="admin/reservations.html",
        context={"active_page": "admin", "restaurant": restaurant, "rows": rows, "total": total,
                 "selected_date": date.isoformat() if date else "", "page_size": page_size,
                 "result": PageResult(rows, total, page, page_size)},
    )


def register_web(app: FastAPI) -> None:
    """HTML 라우터와 정적 파일을 기존 앱에 등록한다."""
    app.mount("/static", StaticFiles(directory=str(SRC_DIR / "static")), name="static")
    app.include_router(router)
