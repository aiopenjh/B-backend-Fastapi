# [담당 5 최지훈] 손님용 식당 목록·상세 화면 테스트 (가짜 식당·빈자리 매니저)
import uuid
from datetime import datetime, timedelta

import httpx
import pytest
from fastapi import FastAPI

from container import create_restaurant_service
from restaurant.domain.exceptions import RestaurantNotFoundError
from restaurant.domain.restaurant import Menu, Restaurant
from slot.application.service import SlotAvailability
from slot.domain.day_range import SEOUL, seoul_now
from slot.domain.time_slot import TimeSlot
from web import register_web
from web_data import get_slot_service

RESTAURANT = Restaurant(
    id=1,
    owner_id=uuid.uuid4(),
    name="테스트 식당",
    address="서울시 중구",
    cuisine="한식",
    menus=[Menu(id=1, name="비빔밥", price=9000)],
)


def make_slot(slot_id: int, hour: int, reserved: int) -> TimeSlot:
    starts_at = datetime(2030, 1, 2, hour, tzinfo=SEOUL)
    return TimeSlot(
        id=slot_id, restaurant_id=1, starts_at=starts_at,
        ends_at=starts_at + timedelta(minutes=90),
        capacity=10, reserved_guests=reserved, max_party_size=4,
    )


class FakeRestaurantService:
    """받은 값을 적어 두고 정해진 식당만 돌려주는 가짜"""

    def __init__(self):
        self.received = None

    async def list_restaurants(self, q, cuisine, sort, page):
        self.received = (q, cuisine, sort, page.page, page.page_size)
        return [RESTAURANT], 1

    async def get_restaurant(self, restaurant_id):
        if restaurant_id != RESTAURANT.id:
            raise RestaurantNotFoundError()
        return RESTAURANT


class FakeSlotService:
    """받은 날짜·인원을 적어 두고 시간대 2개(가능 1, 마감 1)를 돌려주는 가짜"""

    def __init__(self):
        self.received = None

    async def get_availability(self, restaurant_id, day, party_size):
        self.received = (restaurant_id, day, party_size)
        return [
            SlotAvailability(slot=make_slot(1, 18, 0), available=True),
            SlotAvailability(slot=make_slot(2, 20, 10), available=False),
        ]


@pytest.fixture
def fakes():
    return FakeRestaurantService(), FakeSlotService()


@pytest.fixture
def client(fakes) -> httpx.AsyncClient:
    restaurants, slots = fakes
    app = FastAPI()
    register_web(app)
    app.dependency_overrides[create_restaurant_service] = lambda: restaurants
    app.dependency_overrides[get_slot_service] = lambda: slots
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


async def test_browse_page_shows_restaurants_and_passes_filters(client, fakes):
    async with client:
        response = await client.get("/ui/restaurants?q=테스트&cuisine=&sort=name&page=2")

    assert response.status_code == 200
    assert "테스트 식당" in response.text
    assert "/ui/restaurants/1" in response.text  # 상세로 가는 링크
    # 빈 칸(cuisine=)은 '안 고름'(None)으로, 한 페이지 기본 12개
    assert fakes[0].received == ("테스트", None, "name", 2, 12)


async def test_restaurant_page_shows_menus_and_slots(client, fakes):
    async with client:
        response = await client.get("/ui/restaurants/1?date=2030-01-02&party_size=3")

    assert response.status_code == 200
    assert "비빔밥" in response.text and "9,000원" in response.text
    assert "18:00 ~ 19:30" in response.text
    assert "예약 가능" in response.text and "예약 불가" in response.text
    assert fakes[1].received[0] == 1
    assert fakes[1].received[1].isoformat() == "2030-01-02"
    assert fakes[1].received[2] == 3


async def test_restaurant_page_defaults_to_tomorrow_and_two_people(client, fakes):
    async with client:
        response = await client.get("/ui/restaurants/1")

    assert response.status_code == 200
    _, day, party_size = fakes[1].received
    assert day == (seoul_now() + timedelta(days=1)).date()
    assert party_size == 2


async def test_missing_restaurant_page_returns_404_screen(client, fakes):
    async with client:
        response = await client.get("/ui/restaurants/999")

    assert response.status_code == 404
    assert "식당을 찾을 수 없어요" in response.text
    assert fakes[1].received is None  # 없는 식당이면 빈자리는 안 부름
