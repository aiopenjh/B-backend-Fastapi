# [담당 5 최지훈] 화면 로그인(JWT 쿠키)·운영자 화면 문 테스트 (가짜 로그인 매니저·가짜 운영자 매니저)
import uuid

import httpx
import pytest
from fastapi import FastAPI

from auth.application.service import IssuedToken  # 담당1 로그인 결과
from auth.domain.exceptions import InvalidCredentialsError  # 담당1 로그인 실패
from auth.domain.value_object import AuthenticatedUser, AuthRole  # 담당1 로그인한 사람
from common.errors import ForbiddenError  # 공통 403
from container import (
    create_auth_service,
    create_browse_service,
    create_owner_service,
    create_restaurant_service,
)
from restaurant.domain.restaurant import Restaurant  # 담당2 식당
from web import register_web
from web_auth import COOKIE_NAME

OWNER = AuthenticatedUser(user_id=uuid.uuid4(), role=AuthRole.OWNER)
CUSTOMER = AuthenticatedUser(user_id=uuid.uuid4(), role=AuthRole.CUSTOMER)
TOKENS = {"owner-token": OWNER, "customer-token": CUSTOMER}
ACCOUNTS = {"owner@example.com": "owner-token", "customer@example.com": "customer-token"}
PASSWORD = "Aa1!-test-only"


class FakeAuthService:
    """가짜 로그인 매니저: 정해 둔 이메일·비밀번호만 통과, 토큰 → 사람"""

    async def login(self, email, password):
        if email in ACCOUNTS and password == PASSWORD:
            return IssuedToken(access_token=ACCOUNTS[email], expires_in=3600)
        raise InvalidCredentialsError()

    async def authenticate(self, token):
        if token in TOKENS:
            return TOKENS[token]
        raise InvalidCredentialsError()


class FakeOwnerService:
    """가짜 운영자 매니저: 내 식당 1곳, 2번 식당은 남의 식당(403)"""

    async def list_my_restaurants(self, owner, page):
        return [Restaurant(id=1, owner_id=owner.user_id, name="내 식당", address="서울", cuisine="한식")], 1

    async def list_restaurant_reservations(self, owner, restaurant_id, day, page):
        if restaurant_id != 1:
            raise ForbiddenError()
        return [], 0


@pytest.fixture
def client() -> httpx.AsyncClient:
    app = FastAPI()
    register_web(app)
    app.dependency_overrides[create_auth_service] = FakeAuthService
    app.dependency_overrides[create_owner_service] = FakeOwnerService
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


async def test_login_sets_httponly_cookie_and_goes_home(client):
    async with client:
        response = await client.post("/ui/login", data={"username": "owner@example.com", "password": PASSWORD})

    assert response.status_code == 303
    assert response.headers["location"].endswith("/ui/owner/restaurants")  # 운영자 첫 화면
    cookie = response.headers["set-cookie"]
    assert cookie.startswith(f"{COOKIE_NAME}=owner-token")
    assert "HttpOnly" in cookie and "Path=/ui" in cookie and "samesite=lax" in cookie.lower()


async def test_login_returns_to_safe_next_only(client):
    async with client:
        ok = await client.post("/ui/login", data={"username": "customer@example.com", "password": PASSWORD, "next": "/ui/restaurants/3"})
        evil = await client.post("/ui/login", data={"username": "customer@example.com", "password": PASSWORD, "next": "https://evil.example.com"})

    assert ok.headers["location"] == "/ui/restaurants/3"
    assert evil.headers["location"].endswith("/ui/restaurants")  # 바깥 주소는 버리고 손님 첫 화면


async def test_wrong_password_shows_message_without_cookie(client):
    async with client:
        response = await client.post("/ui/login", data={"username": "owner@example.com", "password": "wrong"})

    assert response.status_code == 401
    assert "이메일 또는 비밀번호가 올바르지 않습니다." in response.text
    assert "set-cookie" not in response.headers


async def test_logout_deletes_cookie(client):
    async with client:
        response = await client.post("/ui/logout")

    assert response.status_code == 303
    assert f'{COOKIE_NAME}=""' in response.headers["set-cookie"] or "Max-Age=0" in response.headers["set-cookie"]


async def test_owner_page_without_login_goes_to_login_with_next(client):
    async with client:
        response = await client.get("/ui/owner/restaurants")

    assert response.status_code == 303
    assert "/ui?next=%2Fui%2Fowner%2Frestaurants" in response.headers["location"]


async def test_owner_page_with_owner_cookie_shows_my_restaurants(client):
    client.cookies.set(COOKIE_NAME, "owner-token")
    async with client:
        response = await client.get("/ui/owner/restaurants")

    assert response.status_code == 200
    assert "내 식당" in response.text
    assert "운영자로 로그인" in response.text  # 사이드바 로그인 상태


async def test_owner_page_with_customer_cookie_is_403_page(client):
    client.cookies.set(COOKIE_NAME, "customer-token")
    async with client:
        response = await client.get("/ui/owner/restaurants")

    assert response.status_code == 403
    assert "운영자만 볼 수 있어요" in response.text


async def test_other_restaurant_reservations_is_403_page_not_json(client):
    client.cookies.set(COOKIE_NAME, "owner-token")
    async with client:
        response = await client.get("/ui/owner/restaurants/2/reservations")

    assert response.status_code == 403
    assert "예약을 볼 수 없어요" in response.text
    assert response.headers["content-type"].startswith("text/html")


async def test_broken_cookie_counts_as_not_logged_in(client):
    client.cookies.set(COOKIE_NAME, "forged-token")
    async with client:
        response = await client.get("/ui/owner/restaurants")

    assert response.status_code == 303  # 위조·만료 토큰 → 로그인 화면으로


class FakeBrowseService:
    """가짜 둘러보기 매니저: 지역 칩 없음"""

    async def list_regions(self):
        return []


class FakeRestaurantService:
    """가짜 식당 매니저: 손님 화면이 열리는지만 보려고"""

    async def list_restaurants(self, q, cuisine, sort, page):
        return [], 0


async def test_owner_is_sent_from_customer_pages_to_own_space(client):
    client.cookies.set(COOKIE_NAME, "owner-token")
    async with client:
        browse = await client.get("/ui/restaurants")
        detail = await client.get("/ui/restaurants/1")

    assert browse.status_code == 303 and browse.headers["location"].endswith("/ui/owner/restaurants")
    assert detail.status_code == 303 and detail.headers["location"].endswith("/ui/owner/restaurants")


async def test_menus_are_split_by_role():
    app = FastAPI()
    register_web(app)
    app.dependency_overrides[create_auth_service] = FakeAuthService
    app.dependency_overrides[create_owner_service] = FakeOwnerService
    app.dependency_overrides[create_restaurant_service] = FakeRestaurantService
    app.dependency_overrides[create_browse_service] = FakeBrowseService
    owner = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test", cookies={COOKIE_NAME: "owner-token"})
    customer = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test", cookies={COOKIE_NAME: "customer-token"})
    async with owner, customer:
        owner_page = await owner.get("/ui/owner/restaurants")
        customer_page = await customer.get("/ui/restaurants")

    assert "운영 식당" in owner_page.text and "식당 둘러보기</a>" not in owner_page.text
    assert "운영자 워크스페이스" in owner_page.text
    assert "식당 둘러보기" in customer_page.text and "운영 식당</a>" not in customer_page.text
    assert "손님 화면" in customer_page.text


async def test_forbidden_page_button_goes_to_own_home(client):
    client.cookies.set(COOKIE_NAME, "customer-token")
    async with client:
        response = await client.get("/ui/owner/restaurants")

    assert response.status_code == 403
    assert 'href="http://test/ui/restaurants">첫 화면으로' in response.text  # 손님의 첫 화면
