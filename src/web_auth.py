# [담당 5] 화면 로그인: JWT를 쿠키에 담아, 화면(Jinja)에서도 "누가 로그인했나"를 안다
"""API(/api/v1)는 그대로 헤더(Authorization: Bearer) 방식이다.
화면(/ui)만 같은 JWT를 HttpOnly 쿠키에 담아 들고 다닌다.
JWT 발급·확인은 담당 1 AuthService(login·authenticate)를 그대로 부른다 (담당 1 코드는 고치지 않음).
"""

from typing import Annotated

from fastapi import Depends, Request
from fastapi.responses import RedirectResponse

from auth.application.service import AuthService  # 담당 1: 로그인 매니저
from auth.domain.value_object import AuthenticatedUser  # 담당 1: 로그인한 사람
from common.errors import AppError  # 공통 오류
from container import create_auth_service  # 담당 1: 로그인 매니저 공장

COOKIE_NAME = "ui_access_token"
COOKIE_PATH = "/ui"  # 화면 주소에만 쿠키를 보냄 (API에는 안 감)


async def get_ui_user(
    request: Request,
    auth: Annotated[AuthService, Depends(create_auth_service)],
) -> AuthenticatedUser | None:
    """쿠키의 JWT로 로그인한 사람을 꺼낸다. 없거나 만료·위조·탈퇴면 None (= 로그인 안 함)."""
    token = request.cookies.get(COOKIE_NAME)
    user = None
    if token:
        try:
            user = await auth.authenticate(token=token)
        except AppError:
            user = None
    request.state.ui_user = user  # 사이드바가 로그인 상태를 보여 줄 때 씀
    return user


UIUser = Annotated[AuthenticatedUser | None, Depends(get_ui_user)]


def safe_next(next_url: str | None) -> str | None:
    """로그인 뒤 돌아갈 주소. 우리 화면 주소(/ui...)만 허용하고 바깥 주소는 버린다."""
    if next_url and next_url.startswith("/ui") and not next_url.startswith("//") and "\\" not in next_url:
        return next_url
    return None


def home_url(request: Request, user: AuthenticatedUser) -> str:
    """로그인 뒤 첫 화면: 운영자는 운영 식당, 그 밖에는 식당 둘러보기"""
    if user.is_owner():
        return str(request.url_for("ui_restaurants"))
    return str(request.url_for("ui_browse"))


def to_login(request: Request) -> RedirectResponse:
    """로그인 화면으로 보내고, 로그인하면 지금 보던 화면으로 돌아오게 next를 붙인다."""
    here = request.url.path + (f"?{request.url.query}" if request.url.query else "")
    return RedirectResponse(request.url_for("ui_login").include_query_params(next=here), status_code=303)
