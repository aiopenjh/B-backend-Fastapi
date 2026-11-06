import uuid

import pytest

from common.pagination import PageParams
from restaurant.application.service import RestaurantService
from restaurant.domain.exceptions import RestaurantNotFoundError
from restaurant.domain.restaurant import Restaurant

RESTAURANT = Restaurant(
    id=1,
    owner_id=uuid.uuid4(),
    name="테스트 식당",
    address="서울시 중구",
    cuisine="KOREAN",
)


class FakeRestaurantRepository:
    """DB없이 정해진 값만 돌려주고, 받은 값을 기록하는 가짜 창고"""

    def __init__(self):
        self.received = None  # 서비스가 넘겨준 값을 여기에 적어 둠

    async def find_all(self, q, cuisine, sort, offset, limit):
        self.received = (q, cuisine, sort, offset, limit)
        return [RESTAURANT], 1

    async def find_by_id(self, restaurant_id):
        if restaurant_id == RESTAURANT.id:
            return RESTAURANT
        return None


async def test_list_restaurants_passes_offset_and_limit():
    repo = FakeRestaurantRepository()
    service = RestaurantService(repo=repo)

    items, total = await service.list_restaurants(
        "식당", "KOREAN", "name", PageParams(page=2, page_size=10)
    )

    assert items == [RESTAURANT]
    assert total == 1
    assert repo.received == ("식당", "KOREAN", "name", 10, 10)


async def test_get_missing_restaurant_raise_not_found():
    service = RestaurantService(repo=FakeRestaurantRepository())

    with pytest.raises(RestaurantNotFoundError):
        await service.get_restaurant(999)
