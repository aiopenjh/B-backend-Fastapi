import uuid

import pytest

from auth.domain.value_object import AuthenticatedUser, AuthRole
from common.pagination import PageParams
from restaurant.application.service import RestaurantService
from restaurant.domain.exceptions import (
    MenuNotFoundError,
    NotRestaurantOwnerError,
    RestaurantNotFoundError,
)
from restaurant.domain.restaurant import Menu, Restaurant

RESTAURANT = Restaurant(
    id=1,
    owner_id=uuid.uuid4(),
    name="테스트 식당",
    address="서울시 중구",
    cuisine="KOREAN",
    menus=[Menu(id=10, name="비빔밥", price=9000)],
)

NEW_MENU = Menu(id=11, name="냉면", price=10000)


class FakeRestaurantRepository:
    """DB없이 정해진 값만 돌려주고, 받은 값을 기록하는 가짜 창고"""

    def __init__(self):
        self.received = None  # 서비스가 넘겨준 값을 여기에 적어 둠
        self.updated = None  # update에 뭘 받았는지 기록
        self.menu_changed = None  # 메뉴에 무슨 일을 했는지 기록

    async def find_all(self, q, cuisine, sort, offset, limit):
        self.received = (q, cuisine, sort, offset, limit)
        return [RESTAURANT], 1

    async def find_by_id(self, restaurant_id):
        if restaurant_id == RESTAURANT.id:
            return RESTAURANT
        return None

    async def update(self, restaurant_id, changes):
        self.updated = (restaurant_id, changes)
        return RESTAURANT

    async def add_menu(self, restaurant_id, fields):
        self.menu_changed = ("add", restaurant_id, fields)
        return NEW_MENU

    async def update_menu(self, menu_id, changes):
        self.menu_changed = ("update", menu_id, changes)
        return RESTAURANT.menus[0]

    async def delete_menu(self, menu_id):
        self.menu_changed = ("delete", menu_id)


class FakeUniOfWork:
    """commit이 불렸는지만 기록하는 가짜"""

    def __init__(self):
        self.committed = False

    async def commit(self):
        self.committed = True


async def test_list_restaurants_passes_offset_and_limit():
    repo = FakeRestaurantRepository()
    service = RestaurantService(repo=repo, uow=FakeUniOfWork())

    items, total = await service.list_restaurants(
        "식당", "KOREAN", "name", PageParams(page=2, page_size=10)
    )

    assert items == [RESTAURANT]
    assert total == 1
    assert repo.received == ("식당", "KOREAN", "name", 10, 10)


async def test_get_missing_restaurant_raise_not_found():
    service = RestaurantService(repo=FakeRestaurantRepository(), uow=FakeUniOfWork())

    with pytest.raises(RestaurantNotFoundError):
        await service.get_restaurant(999)


OWNER = AuthenticatedUser(user_id=RESTAURANT.owner_id, role=AuthRole.OWNER)


async def test_owner_updates_own_restaurant():
    repo = FakeRestaurantRepository()
    uow = FakeUniOfWork()
    service = RestaurantService(repo=repo, uow=uow)

    await service.update_restaurant(OWNER, 1, {"name": "새 이름"})

    assert repo.updated == (1, {"name": "새 이름"})
    assert uow.committed is True


async def test_update_missing_restaurant_raises_not_found():
    uow = FakeUniOfWork()
    service = RestaurantService(repo=FakeRestaurantRepository(), uow=uow)

    with pytest.raises(RestaurantNotFoundError):
        await service.update_restaurant(OWNER, 999, {"name": "새 이름"})

    assert uow.committed is False


async def test_other_owner_cannot_update_restaurant():
    repo = FakeRestaurantRepository()
    uow = FakeUniOfWork()
    service = RestaurantService(repo=repo, uow=uow)
    other_owner = AuthenticatedUser(user_id=uuid.uuid4(), role=AuthRole.OWNER)

    with pytest.raises(NotRestaurantOwnerError):
        await service.update_restaurant(other_owner, 1, {"name": "새 이름"})

    assert repo.updated is None
    assert uow.committed is False


async def test_owner_adds_menus():
    repo = FakeRestaurantRepository()
    uow = FakeUniOfWork()
    service = RestaurantService(repo=repo, uow=uow)

    menu = await service.add_menu(OWNER, 1, {"name": "냉면", "price": 10000})

    assert menu == NEW_MENU
    assert repo.menu_changed == ("add", 1, {"name": "냉면", "price": 10000})
    assert uow.committed is True


async def test_other_owner_cannot_add_menu():
    repo = FakeRestaurantRepository()
    uow = FakeUniOfWork()
    service = RestaurantService(repo=repo, uow=uow)
    other_owner = AuthenticatedUser(user_id=uuid.uuid4(), role=AuthRole.OWNER)

    with pytest.raises(NotRestaurantOwnerError):
        await service.add_menu(other_owner, 1, {"name": "냉면", "price": 10000})

    assert repo.menu_changed is None
    assert uow.committed is False


async def test_owner_updates_menus():
    repo = FakeRestaurantRepository()
    uow = FakeUniOfWork()
    service = RestaurantService(repo=repo, uow=uow)

    await service.update_menu(OWNER, 1, 10, {"price": 9500})

    assert repo.menu_changed == ("update", 10, {"price": 9500})
    assert uow.committed is True


async def test_update_missing_menu_raises_not_found():
    repo = FakeRestaurantRepository()
    uow = FakeUniOfWork()
    service = RestaurantService(repo=repo, uow=uow)

    with pytest.raises(MenuNotFoundError):
        await service.update_menu(OWNER, 1, 99, {"price": 9500})

    assert repo.menu_changed is None
    assert uow.committed is False


async def test_owner_deletes_menu():
    repo = FakeRestaurantRepository()
    uow = FakeUniOfWork()
    service = RestaurantService(repo=repo, uow=uow)

    await service.delete_menu(OWNER, 1, 10)

    assert repo.menu_changed == ("delete", 10)
    assert uow.committed is True


async def test_delete_menu_of_missing_restaurant_raises_not_found():
    uow = FakeUniOfWork()
    service = RestaurantService(repo=FakeRestaurantRepository(), uow=uow)

    with pytest.raises(RestaurantNotFoundError):
        await service.delete_menu(OWNER, 999, 10)

    assert uow.committed is False
