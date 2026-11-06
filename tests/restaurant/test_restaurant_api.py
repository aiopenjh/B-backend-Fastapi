import uuid

import httpx
import pytest
from fastapi import FastAPI

from common.error_handlers import register_error_handlers
from container import create_restaurant_service
from restaurant.domain.exceptions import RestaurantNotFoundError
from restaurant.domain.restaurant import Menu, Restaurant
from restaurant.presentation.routers.v1.router import router

RESTAURANT = Restaurant(
    id=1,
    owner_id=uuid.uuid4(),
    name="테스트 식당",
    address="서울시 중구",
    cuisine="KOREAN",
    menus=[Menu(id=1, name="비빔밥", price=9000)],
)


class FakeRestaurantService:
    """DB없이 정해진 값만 돌려주는 가짜 서비스"""

    async def list_restaurants(self, q, cuisine, sort, page):
        return [RESTAURANT], 1

    async def get_restaurant(self, restaurant_id):
        if restaurant_id != RESTAURANT.id:
            raise RestaurantNotFoundError()
        return RESTAURANT


@pytest.fixture
def client() -> httpx.AsyncClient:
    app = FastAPI()
    register_error_handlers(app)
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[create_restaurant_service] = FakeRestaurantService
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    )


async def test_list_restaurants_returns_page(client):
    async with client:
        response = await client.get("/api/v1/restaurants?page=2&page_size=10")

    body = response.json()
    assert response.status_code == 200
    assert body["success"] is True
    assert body["data"]["page"] == 2
    assert body["data"]["page_size"] == 10
    assert body["data"]["total"] == 1
    assert body["data"]["items"][0]["name"] == "테스트 식당"
    assert "owner_id" not in body["data"]["items"][0]


async def test_get_restaurant_returns_detail_with_menus(client):
    async with client:
        response = await client.get("/api/v1/restaurants/1")

    body = response.json()
    assert response.status_code == 200
    assert body["data"]["address"] == "서울시 중구"
    assert body["data"]["menus"][0]["name"] == "비빔밥"


async def test_get_missing_restaurant_returns_404(client):
    async with client:
        response = await client.get("/api/v1/restaurants/999")

    body = response.json()
    assert response.status_code == 404
    assert body["success"] is False
    assert body["code"] == "RESTAURANT_NOT_FOUND"


async def test_unknown_sort_returns_422(client):
    async with client:
        response = await client.get("/api/v1/restaurants?sort=newest")

    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"
