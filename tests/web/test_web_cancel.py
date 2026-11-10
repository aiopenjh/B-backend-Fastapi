# [담당 5 최지훈] 화면 예약 취소(손님 내 예약·운영자·관리자 예약 표) 테스트 (가짜 로그인·가짜 매니저)
import uuid
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from fastapi import FastAPI, Request

from admin.infrastructure.query_repository import Guest  # 담당 5 관리자 화면 예약자
from auth.domain.value_object import AuthenticatedUser, AuthRole  # 담당1 로그인한 사람
from common.errors import NotFoundError  # 공통 404
from container import (
    create_admin_service,
    create_owner_service,
    create_reservation_query_service,
    create_reservation_service,
    create_restaurant_service,
)
from reservation.domain.exceptions import AlreadyCancelledError  # 담당4 이미 취소
from reservation.domain.reservation import Reservation, ReservationStatus  # 담당4 예약
from restaurant.domain.restaurant import Restaurant  # 담당2 식당
from slot.domain.time_slot import TimeSlot  # 담당3 시간대
from web import register_web
from web_auth import get_ui_user

CUSTOMER = AuthenticatedUser(user_id=uuid.uuid4(), role=AuthRole.CUSTOMER)
OWNER = AuthenticatedUser(user_id=uuid.uuid4(), role=AuthRole.OWNER)
ADMIN = AuthenticatedUser(user_id=uuid.uuid4(), role=AuthRole.ADMIN)
RESTAURANT = Restaurant(id=1, owner_id=OWNER.user_id, name="을지로 한상", address="서울 중구", cuisine="KOREAN")
FUTURE = datetime.now(UTC) + timedelta(days=1)
PAST = datetime.now(UTC) - timedelta(days=1)


def slot(slot_id, starts_at):
    return TimeSlot(id=slot_id, restaurant_id=1, starts_at=starts_at, ends_at=starts_at + timedelta(minutes=90),
                    capacity=10, reserved_guests=2, max_party_size=4)


def reservation(reservation_id, status=ReservationStatus.CONFIRMED):
    return Reservation(id=reservation_id, user_id=CUSTOMER.user_id, slot_id=reservation_id, party_size=2,
                       status=status, created_at=PAST - timedelta(days=1))


ROWS = [
    (reservation(11), slot(11, FUTURE)),  # 시작 전 확정 → 취소 버튼
    (reservation(12), slot(12, PAST)),  # 이미 지난 확정 → 버튼 없음
    (reservation(13, ReservationStatus.CANCELLED), slot(13, FUTURE)),  # 취소됨 → 버튼 없음
]


class FakeBooking:
    """가짜 예약 매니저: 받은 취소를 적어 두고, 12번은 이미 취소, 99번은 없는 예약"""

    def __init__(self):
        self.cancelled = []

    async def cancel(self, user, reservation_id, now):
        if reservation_id == 12:
            raise AlreadyCancelledError()
        if reservation_id == 99:
            raise NotFoundError()
        self.cancelled.append((user.role, reservation_id))
        return ROWS[0]


class FakeMyReservations:
    async def list_my_reservations(self, me, status, page):
        return ROWS, len(ROWS)


class FakeRestaurants:
    async def get_restaurant(self, restaurant_id):
        return RESTAURANT


class FakeOwnerService:
    async def list_restaurant_reservations(self, owner, restaurant_id, day, page):
        return ROWS, len(ROWS)


class FakeAdmin:
    async def list_restaurant_reservations(self, restaurant_id, day, page):
        guest = Guest(name="손님A", email="guest@example.com", phone="010-1111-0001")
        return RESTAURANT, [(r, s, guest) for r, s in ROWS], len(ROWS)


def login_as(user):
    def fake(request: Request):
        request.state.ui_user = user
        return user
    return fake


@pytest.fixture
def booking():
    return FakeBooking()


def make_client(booking, user):
    app = FastAPI()
    register_web(app)
    app.dependency_overrides[create_reservation_service] = lambda: booking
    app.dependency_overrides[create_reservation_query_service] = FakeMyReservations
    app.dependency_overrides[create_restaurant_service] = FakeRestaurants
    app.dependency_overrides[create_owner_service] = FakeOwnerService
    app.dependency_overrides[create_admin_service] = FakeAdmin
    app.dependency_overrides[get_ui_user] = login_as(user)
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


async def test_cancel_without_login_goes_to_login(booking):
    async with make_client(booking, None) as client:
        response = await client.post("/ui/reservations/11/cancel", data={"next": "/ui/my/reservations"})

    assert response.status_code == 303
    assert "/ui?next=" in response.headers["location"]
    assert booking.cancelled == []


async def test_customer_cancels_and_comes_back_with_notice(booking):
    async with make_client(booking, CUSTOMER) as client:
        response = await client.post("/ui/reservations/11/cancel", data={"next": "/ui/my/reservations"})
        page = await client.get(response.headers["location"])

    assert response.headers["location"] == "/ui/my/reservations?cancelled=11"
    assert booking.cancelled == [(AuthRole.CUSTOMER, 11)]  # 권한 판단은 담당 4 매니저가 함
    assert "예약 #11을 취소했어요" in page.text


async def test_cancel_failure_shows_reason(booking):
    async with make_client(booking, CUSTOMER) as client:
        already = await client.post("/ui/reservations/12/cancel", data={"next": "/ui/my/reservations"})
        missing = await client.post("/ui/reservations/99/cancel", data={"next": "/ui/my/reservations"})
        page = await client.get(already.headers["location"])

    assert already.headers["location"].endswith("cancel_fail=ALREADY_CANCELLED")
    assert missing.headers["location"].endswith("cancel_fail=NOT_FOUND")
    assert "이미 취소된 예약이에요." in page.text


async def test_cancel_ignores_outside_next(booking):
    async with make_client(booking, CUSTOMER) as client:
        response = await client.post("/ui/reservations/11/cancel", data={"next": "https://evil.example.com"})

    assert response.headers["location"].startswith("http://test/ui/restaurants")  # 바깥 주소 대신 손님 첫 화면


async def test_my_reservations_page_shows_cancel_only_for_upcoming(booking):
    async with make_client(booking, CUSTOMER) as client:
        response = await client.get("/ui/my/reservations")

    assert response.status_code == 200
    assert "을지로 한상" in response.text
    assert response.text.count("/ui/reservations/11/cancel") == 1  # 시작 전 확정만 취소 버튼
    assert "/ui/reservations/12/cancel" not in response.text and "/ui/reservations/13/cancel" not in response.text
    assert "방문 시간 지남" in response.text and "취소됨" in response.text
    assert "내 예약</a>" in response.text  # 손님 탭 바에 내 예약


async def test_my_reservations_needs_login_and_sends_owner_home(booking):
    async with make_client(booking, None) as anonymous:
        not_logged = await anonymous.get("/ui/my/reservations")
    async with make_client(booking, OWNER) as owner:
        by_owner = await owner.get("/ui/my/reservations")

    assert "/ui?next=" in not_logged.headers["location"]
    assert by_owner.headers["location"].endswith("/ui/owner/restaurants")


async def test_owner_and_admin_tables_have_cancel_buttons(booking):
    async with make_client(booking, OWNER) as owner:
        owner_page = await owner.get("/ui/owner/restaurants/1/reservations")
    async with make_client(booking, ADMIN) as admin:
        admin_page = await admin.get("/ui/admin/restaurants/1/reservations")

    for page in (owner_page, admin_page):
        assert page.status_code == 200
        assert page.text.count("/ui/reservations/11/cancel") == 1
        assert "/ui/reservations/12/cancel" not in page.text
    assert "한식" in admin_page.text  # 음식 종류는 한국어로
