# [담당 5 최지훈] 화면 예약하기 테스트: 로그인·역할 확인, 다른 식당 시간대 막기, 실패 문구, 완료 안내 (가짜 매니저)
import uuid
from datetime import UTC, date, datetime, timedelta

import httpx
import pytest
from fastapi import FastAPI, Request

from auth.domain.value_object import AuthenticatedUser, AuthRole
from container import (
    create_browse_service,
    create_reservation_query_service,
    create_reservation_service,
    create_restaurant_service,
    create_slot_service,
)
from reservation.domain.reservation import Reservation, ReservationStatus
from restaurant.domain.exceptions import RestaurantNotFoundError
from restaurant.domain.restaurant import Restaurant
from slot.application.service import SlotAvailability
from slot.domain.exceptions import SlotSoldOut
from slot.domain.time_slot import TimeSlot
from web import register_web
from web_auth import get_ui_user

CUSTOMER = AuthenticatedUser(user_id=uuid.uuid4(), role=AuthRole.CUSTOMER)
ADMIN = AuthenticatedUser(user_id=uuid.uuid4(), role=AuthRole.ADMIN)
RESTAURANT = Restaurant(id=1, owner_id=uuid.uuid4(), name="을지로 한상", address="서울 중구", cuisine="한식")
STARTS = datetime(2030, 1, 2, 3, 0, tzinfo=UTC)  # 서울 12:00
SLOT = TimeSlot(id=7, restaurant_id=1, starts_at=STARTS, ends_at=STARTS + timedelta(minutes=90),
                capacity=10, reserved_guests=2, max_party_size=4)
RESERVATION = Reservation(id=55, user_id=CUSTOMER.user_id, slot_id=7, party_size=2,
                          status=ReservationStatus.CONFIRMED, created_at=STARTS - timedelta(days=1))


class FakeRestaurants:
    async def get_restaurant(self, restaurant_id):
        return RESTAURANT


class FakeSlots:
    async def get_availability(self, restaurant_id, day, party_size):
        return [SlotAvailability(slot=SLOT, available=True)]


class FakeBrowse:
    async def next_open_day(self, restaurant_id, after):
        return None


class FakeBooking:
    """가짜 예약 매니저: 받은 값을 적어 두고, sold_out이면 자리 부족 오류"""

    def __init__(self):
        self.received = None
        self.sold_out = False

    async def create(self, user_id, slot_id, party_size, contact_phone, now):
        self.received = (user_id, slot_id, party_size)
        if self.sold_out:
            raise SlotSoldOut()
        return RESERVATION, SLOT


class FakeMyReservations:
    async def get_reservation(self, me, reservation_id):
        return RESERVATION, SLOT


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
    app.dependency_overrides[create_restaurant_service] = FakeRestaurants
    app.dependency_overrides[create_slot_service] = FakeSlots
    app.dependency_overrides[create_browse_service] = FakeBrowse
    app.dependency_overrides[create_reservation_query_service] = FakeMyReservations
    app.dependency_overrides[create_reservation_service] = lambda: booking
    app.dependency_overrides[get_ui_user] = login_as(user)
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


FORM = {"slot_id": "7", "party_size": "2", "date": "2030-01-02"}


async def test_not_logged_in_goes_to_login_and_comes_back_to_same_choice(booking):
    async with make_client(booking, None) as client:
        response = await client.post("/ui/restaurants/1/reserve", data=FORM)

    assert response.status_code == 303
    location = response.headers["location"]
    assert "/ui?next=" in location and "slot_id%3D7" in location and "date%3D2030-01-02" in location
    assert booking.received is None


async def test_customer_books_and_sees_done_notice(booking):
    async with make_client(booking, CUSTOMER) as client:
        response = await client.post("/ui/restaurants/1/reserve", data=FORM)
        done = await client.get(response.headers["location"])

    assert response.status_code == 303 and "reserved=55" in response.headers["location"]
    assert booking.received == (CUSTOMER.user_id, 7, 2)
    assert "예약됐어요" in done.text and "#55" in done.text and "2030.01.02  12:00" in done.text


async def test_slot_of_other_restaurant_is_refused(booking):
    async with make_client(booking, CUSTOMER) as client:
        response = await client.post("/ui/restaurants/1/reserve", data={**FORM, "slot_id": "999"})

    assert "fail=NOT_THIS_RESTAURANT" in response.headers["location"]
    assert booking.received is None  # 예약 매니저는 부르지 않음


async def test_sold_out_shows_friendly_message(booking):
    booking.sold_out = True
    async with make_client(booking, CUSTOMER) as client:
        response = await client.post("/ui/restaurants/1/reserve", data=FORM)
        page = await client.get(response.headers["location"])

    assert "fail=SLOT_SOLD_OUT" in response.headers["location"]
    assert "방금 자리가 찼어요" in page.text


async def test_admin_cannot_book(booking):
    async with make_client(booking, ADMIN) as client:
        response = await client.post("/ui/restaurants/1/reserve", data=FORM)
        page = await client.get("/ui/restaurants/1?date=2030-01-02")

    assert response.status_code == 403 and "손님 계정으로 예약할 수 있어요" in response.text
    assert booking.received is None
    assert "명 예약하기</button>" not in page.text  # 관리자 화면에는 예약 버튼 없음


async def test_next_open_day_link_when_no_time_left(booking):
    class NoSlots:
        async def get_availability(self, restaurant_id, day, party_size):
            return []

    class Browse:
        async def next_open_day(self, restaurant_id, after):
            return date(2030, 1, 5)

    async with make_client(booking, CUSTOMER) as client:
        client._transport.app.dependency_overrides[create_slot_service] = NoSlots
        client._transport.app.dependency_overrides[create_browse_service] = Browse
        page = await client.get("/ui/restaurants/1?date=2030-01-02")

    assert "이 날은 예약 가능한 시간이 없어요" in page.text
    assert "date=2030-01-05" in page.text


class DeletedRestaurantSlots:
    async def get_availability(self, restaurant_id, day, party_size):
        raise RestaurantNotFoundError()


async def test_booking_deleted_restaurant_shows_page_not_json(booking):
    async with make_client(booking, CUSTOMER) as client:
        client._transport.app.dependency_overrides[create_slot_service] = DeletedRestaurantSlots
        response = await client.post("/ui/restaurants/1/reserve", data=FORM)

    assert response.status_code == 404
    assert response.headers["content-type"].startswith("text/html")  # JSON 대신 안내 화면
    assert "식당을 찾을 수 없어요" in response.text
    assert booking.received is None  # 예약 매니저는 부르지 않음


async def test_too_big_page_is_422(booking):
    async with make_client(booking, CUSTOMER) as client:
        response = await client.get("/ui/restaurants", params={"page": 10**18})

    assert response.status_code == 422


async def test_group_note_shows_max_party_and_phone(booking):
    async with make_client(booking, CUSTOMER) as client:
        response = await client.get("/ui/restaurants/1", params={"date": "2030-01-02"})

    assert "한 번에 최대 4명까지 예약할 수 있어요." in response.text  # 그날 시간대의 최대 인원
    assert "단체는 식당에 전화로 문의해 주세요" in response.text
