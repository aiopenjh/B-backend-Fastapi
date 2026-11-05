"""기존 조회 흐름을 위한 HTML 화면. 인증·실제 데이터 연결은 후속 작업이다."""

from datetime import date as Date, datetime
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, FastAPI, Path as PathParam, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BeforeValidator
from common.schemas import SEOUL
from web_data import OwnerUIQueries, get_owner_ui_queries

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


templates.env.filters["seoul_datetime"] = seoul_datetime
OwnerQueries = Annotated[OwnerUIQueries | None, Depends(get_owner_ui_queries)]
PageNumber = Annotated[int, Query(ge=1)]
PageSize = Annotated[int, Query(ge=1, le=100)]


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


def register_web(app: FastAPI) -> None:
    """HTML 라우터와 정적 파일을 기존 앱에 등록한다."""
    app.mount("/static", StaticFiles(directory=str(SRC_DIR / "static")), name="static")
    app.include_router(router)
