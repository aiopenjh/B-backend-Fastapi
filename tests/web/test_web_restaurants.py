# [담당 5 최지훈] 손님용 식당 목록·상세 화면 테스트 (가짜 식당·빈자리 매니저)
import re
import uuid
from datetime import datetime, timedelta

import httpx
import pytest
from fastapi import FastAPI, Request

from container import (
    create_browse_service,
    create_reservation_query_service,
    create_reservation_service,
    create_restaurant_service,
    create_slot_service,
)
from restaurant.domain.exceptions import RestaurantNotFoundError
from restaurant.domain.restaurant import Menu, Restaurant
from slot.application.service import SlotAvailability
from slot.domain.day_range import SEOUL, seoul_now
from slot.domain.time_slot import TimeSlot
from web import register_web
from web_auth import get_ui_user

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


class FakeBrowseService:
    """가짜 둘러보기 매니저: 음식 종류·시·도·구 목록, 받은 조건과 섞기 번호를 적어 둠"""

    def __init__(self):
        self.received = None
        self.seeds = []
        self.districts_for = None

    def list_provinces(self):
        return ["서울특별시", "경기도"]

    async def list_districts(self, province):
        self.districts_for = province
        return ["관악구", "종로구"]

    async def list_cuisines(self):
        return ["양식", "한식"]

    async def next_open_day(self, restaurant_id, after):
        return None

    async def list_restaurants(self, province, district, q, cuisine, seed, page):
        self.received = (province, district, q, cuisine, page.page, page.page_size)
        self.seeds.append(seed)
        return [RESTAURANT], 12


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


def not_logged_in(request: Request):
    """가짜 화면 문지기: 로그인 안 한 상태"""
    request.state.ui_user = None


@pytest.fixture
def fakes():
    return FakeRestaurantService(), FakeSlotService(), FakeBrowseService()


@pytest.fixture
def client(fakes) -> httpx.AsyncClient:
    restaurants, slots, browse = fakes
    app = FastAPI()
    register_web(app)
    app.dependency_overrides[create_restaurant_service] = lambda: restaurants
    app.dependency_overrides[create_slot_service] = lambda: slots
    app.dependency_overrides[create_browse_service] = lambda: browse
    app.dependency_overrides[create_reservation_query_service] = lambda: None
    app.dependency_overrides[create_reservation_service] = lambda: None
    app.dependency_overrides[get_ui_user] = not_logged_in  # 쿠키 로그인 없이
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


async def test_browse_page_shows_restaurants_and_passes_filters(client, fakes):
    async with client:
        response = await client.get("/ui/restaurants?q=테스트&cuisine=&region=&district=관악구&page=2")

    assert response.status_code == 200
    assert "테스트 식당" in response.text
    assert "/ui/restaurants/1" in response.text  # 상세로 가는 링크
    # 빈 칸은 '안 고름'(None), 지역이 없으면 상세 지역도 무시, 한 페이지 기본 10개
    assert fakes[2].received == (None, None, "테스트", None, 2, 10)
    assert '<option value="한식"' in response.text and '<option value="경기도"' in response.text
    assert 'id="district" name="district" disabled' in response.text  # 지역을 안 고르면 상세 지역 잠김
    assert "number-tag" not in response.text  # 식당 개수는 안 보임


async def test_restaurant_page_shows_menus_and_slots(client, fakes):
    async with client:
        response = await client.get("/ui/restaurants/1?date=2030-01-02&party_size=3")

    assert response.status_code == 200
    assert "비빔밥" in response.text and "9,000원" in response.text
    assert "예약하기" in response.text and "빈자리" not in response.text
    assert "18:00" in response.text and "남은 10석" in response.text  # 고를 수 있는 시간: 남은 자리
    assert "마감" in response.text  # 꽉 찬 20:00은 이유와 함께 비활성
    assert re.search(r'value="2" required\s+disabled', response.text)  # 꽉 찬 시간은 고를 수 없음
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


async def test_region_and_district_show_that_area_10_at_a_time(client, fakes):
    async with client:
        response = await client.get("/ui/restaurants?region=서울특별시&district=관악구&cuisine=한식&page=2")

    assert response.status_code == 200
    assert fakes[2].received == ("서울특별시", "관악구", None, "한식", 2, 10)
    assert fakes[2].districts_for == "서울특별시"  # 고른 시·도의 구만 상세 지역에
    assert '<option value="관악구" selected>' in response.text
    assert "서울특별시 관악구" in response.text


async def test_order_is_reshuffled_on_every_load(client, fakes):
    async with client:
        await client.get("/ui/restaurants")
        again = await client.get("/ui/restaurants")

    assert len(set(fakes[2].seeds)) == 2  # 새로 열 때마다 새 섞기 번호
    assert f"seed={fakes[2].seeds[-1]}" in again.text  # 다음 쪽 링크에 이번 섞기 번호가 실림
    assert "set-cookie" not in again.headers  # 둘러보기는 쿠키를 쓰지 않음


async def test_next_page_keeps_same_order(client, fakes):
    async with client:
        await client.get("/ui/restaurants?seed=abc123&page=2")

    assert fakes[2].seeds[-1] == "abc123"  # 쪽을 넘기면 같은 섞기 번호 → 1쪽과 겹치지 않음


async def test_bad_seed_is_422(client):
    async with client:
        response = await client.get("/ui/restaurants?seed=<script>")

    assert response.status_code == 422
