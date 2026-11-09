# [담당 5 최지훈] 관리자 화면 테스트: 문(로그인·관리자만), 운영자 → 식당 → 날짜별 예약 + 예약자 (가짜 매니저)
import uuid
from datetime import UTC, date, datetime, timedelta

import httpx
import pytest
from fastapi import FastAPI

from admin.infrastructure.query_repository import Guest  # 담당5 예약자 정보
from auth.application.service import IssuedToken  # 담당1 로그인 결과
from auth.domain.exceptions import InvalidCredentialsError  # 담당1 로그인 실패
from auth.domain.value_object import AuthenticatedUser, AuthRole  # 담당1 로그인한 사람
from common.errors import NotFoundError  # 공통 404
from container import create_admin_service, create_auth_service
from reservation.domain.reservation import Reservation, ReservationStatus  # 담당4 예약
from restaurant.domain.restaurant import Restaurant  # 담당2 식당
from slot.domain.time_slot import TimeSlot  # 담당3 슬롯
from user.domain.user import Role, User  # 담당1 회원
from user.domain.value_object import Email  # 담당1 이메일
from web import register_web
from web_auth import COOKIE_NAME

ADMIN = AuthenticatedUser(user_id=uuid.uuid4(), role=AuthRole.ADMIN)
OWNER_LOGIN = AuthenticatedUser(user_id=uuid.uuid4(), role=AuthRole.OWNER)
TOKENS = {"admin-token": ADMIN, "owner-token": OWNER_LOGIN}
PASSWORD = "Aa1!-test-only"

OWNER = User(id=uuid.uuid4(), email=Email("owner.a@example.com"), name="운영자A", password_hash="x",
             phone="010-1111-2222", role=Role.OWNER, created_at=datetime(2026, 11, 1, tzinfo=UTC))
RESTAURANT = Restaurant(id=7, owner_id=OWNER.id, name="을지로 한상", address="서울 중구", cuisine="한식")
STARTS = datetime(2030, 1, 2, 3, 0, tzinfo=UTC)  # 서울 12:00
SLOT = TimeSlot(id=1, restaurant_id=7, starts_at=STARTS, ends_at=STARTS + timedelta(minutes=90),
                capacity=10, reserved_guests=2, max_party_size=4)
RESERVATION = Reservation(id=55, user_id=uuid.uuid4(), slot_id=1, party_size=2, status=ReservationStatus.CONFIRMED,
                          created_at=STARTS - timedelta(days=1))


class FakeAuthService:
    async def login(self, email, password):
        if email == "admin@example.com" and password == PASSWORD:
            return IssuedToken(access_token="admin-token", expires_in=3600)
        raise InvalidCredentialsError()

    async def authenticate(self, token):
        if token in TOKENS:
            return TOKENS[token]
        raise InvalidCredentialsError()


class FakeAdminService:
    """가짜 관리자 매니저: 운영자 1명(식당 1곳), 7번 식당 예약 1건. 받은 날짜를 적어 둠"""

    def __init__(self):
        self.day = "안 부름"

    async def list_owners(self, page):
        return [(OWNER, 1)], 1

    async def list_owner_restaurants(self, owner_id, page):
        if owner_id != OWNER.id:
            raise NotFoundError()
        return OWNER, [RESTAURANT], 1

    async def list_restaurant_reservations(self, restaurant_id, day, page):
        self.day = day
        if restaurant_id != RESTAURANT.id:
            raise NotFoundError()
        return RESTAURANT, [(RESERVATION, SLOT, Guest(name="손님1", email="guest1@example.com", phone="010-9"))], 1


@pytest.fixture
def admin_service():
    return FakeAdminService()


@pytest.fixture
def client(admin_service) -> httpx.AsyncClient:
    app = FastAPI()
    register_web(app)
    app.dependency_overrides[create_auth_service] = FakeAuthService
    app.dependency_overrides[create_admin_service] = lambda: admin_service
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


async def test_admin_login_goes_to_owner_list(client):
    async with client:
        response = await client.post("/ui/login", data={"username": "admin@example.com", "password": PASSWORD})

    assert response.status_code == 303
    assert response.headers["location"].endswith("/ui/admin/owners")


async def test_admin_pages_need_login(client):
    async with client:
        response = await client.get("/ui/admin/owners")

    assert response.status_code == 303
    assert "/ui?next=%2Fui%2Fadmin%2Fowners" in response.headers["location"]


async def test_owner_cannot_open_admin_pages(client):
    client.cookies.set(COOKIE_NAME, "owner-token")
    async with client:
        response = await client.get("/ui/admin/owners")

    assert response.status_code == 403
    assert "관리자만 볼 수 있어요" in response.text


async def test_owner_list_shows_restaurant_count_and_link(client):
    client.cookies.set(COOKIE_NAME, "admin-token")
    async with client:
        response = await client.get("/ui/admin/owners")

    assert response.status_code == 200
    assert "운영자A" in response.text and "owner.a@example.com" in response.text
    assert f"/ui/admin/owners/{OWNER.id}/restaurants" in response.text
    assert "관리자로 로그인" in response.text  # 사이드바


async def test_owner_restaurants_and_unknown_owner(client):
    client.cookies.set(COOKIE_NAME, "admin-token")
    async with client:
        ok = await client.get(f"/ui/admin/owners/{OWNER.id}/restaurants")
        missing = await client.get(f"/ui/admin/owners/{uuid.uuid4()}/restaurants")

    assert ok.status_code == 200
    assert "을지로 한상" in ok.text and "/ui/admin/restaurants/7/reservations" in ok.text
    assert missing.status_code == 404
    assert "운영자를 찾을 수 없어요" in missing.text


async def test_reservations_show_guest_and_seoul_time(client, admin_service):
    client.cookies.set(COOKIE_NAME, "admin-token")
    async with client:
        response = await client.get("/ui/admin/restaurants/7/reservations?date=2030-01-02")

    assert response.status_code == 200
    assert "손님1" in response.text and "guest1@example.com" in response.text
    assert "2030.01.02  12:00" in response.text  # UTC 03:00 → 서울 12:00
    assert "예약 확정" in response.text
    assert admin_service.day == date(2030, 1, 2)


async def test_empty_date_means_all_days_and_unknown_restaurant_is_404(client, admin_service):
    client.cookies.set(COOKIE_NAME, "admin-token")
    async with client:
        all_days = await client.get("/ui/admin/restaurants/7/reservations?date=")
        day_after_all = admin_service.day
        missing = await client.get("/ui/admin/restaurants/999/reservations")

    assert all_days.status_code == 200
    assert day_after_all is None
    assert missing.status_code == 404
    assert "식당을 찾을 수 없어요" in missing.text


async def test_admin_sees_both_customer_pages_and_admin_pages(client):
    client.cookies.set(COOKIE_NAME, "admin-token")
    async with client:
        owners = await client.get("/ui/admin/owners")
        owner_space = await client.get("/ui/owner/restaurants")

    assert "관리자 백오피스" in owners.text
    assert "관리자</a>" in owners.text and "식당 둘러보기</a>" in owners.text  # 둘 다 보임
    assert "운영 식당</a>" not in owners.text
    # 운영자 화면은 "본인 식당"만이라, 관리자는 관리자 화면(모든 운영자)으로 보냄
    assert owner_space.status_code == 303 and owner_space.headers["location"].endswith("/ui/admin/owners")


async def test_admin_can_open_customer_browse(client):
    from container import create_restaurant_service

    class FakeRestaurantService:
        async def list_restaurants(self, q, cuisine, sort, page):
            return [], 0

    client._transport.app.dependency_overrides[create_restaurant_service] = FakeRestaurantService
    client.cookies.set(COOKIE_NAME, "admin-token")
    async with client:
        browse = await client.get("/ui/restaurants")

    assert browse.status_code == 200  # 손님 화면에서 돌려보내지 않음
    assert "손님 화면" in browse.text
