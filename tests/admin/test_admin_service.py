# [담당 5 최지훈] 관리자 매니저 테스트: 404 판단, 창고에 페이지 넘기기 (가짜 창고)
import uuid
from datetime import date

import pytest

from admin.application.service import AdminService  # 담당5 시험할 매니저
from admin.infrastructure.query_repository import Guest  # 담당5 예약자 정보
from common.errors import NotFoundError  # 공통 404
from common.pagination import PageParams  # 담당2 페이지 정보
from restaurant.domain.restaurant import Restaurant  # 담당2 식당

OWNER_ID = uuid.uuid4()
RESTAURANT = Restaurant(id=1, owner_id=OWNER_ID, name="테스트 식당", address="서울", cuisine="한식")


class FakeAdminQueryRepository:
    """DB 없이 받은 값을 적어 두는 가짜 관리자 창고"""

    def __init__(self):
        self.received = None

    async def list_owners(self, offset, limit):
        self.received = (offset, limit)
        return [("운영자", 2)], 1

    async def get_owner(self, owner_id):
        return "운영자A" if owner_id == OWNER_ID else None

    async def list_reservations(self, restaurant_id, day, offset, limit):
        self.received = (restaurant_id, day, offset, limit)
        return [("예약", "슬롯", Guest(name="손님", email="g@example.com", phone="010"))], 1


class FakeOwnerQueryRepository:
    """운영자 창고 가짜: 1번 식당만 있음"""

    async def get_restaurant(self, restaurant_id):
        return RESTAURANT if restaurant_id == RESTAURANT.id else None

    async def list_restaurants(self, owner_id, offset, limit):
        return [RESTAURANT], 1


@pytest.fixture
def service():
    s = AdminService(db=None)
    s.query = FakeAdminQueryRepository()
    s.restaurants = FakeOwnerQueryRepository()
    return s


async def test_list_owners_passes_offset_and_limit(service):
    _, total = await service.list_owners(PageParams(page=3, page_size=10))

    assert service.query.received == (20, 10)  # 3페이지·10개씩 → 20개 건너뜀
    assert total == 1


async def test_owner_restaurants_returns_owner_and_items(service):
    owner, items, total = await service.list_owner_restaurants(OWNER_ID, PageParams(page=1, page_size=20))

    assert owner == "운영자A"
    assert items == [RESTAURANT]
    assert total == 1


async def test_unknown_owner_raises_not_found(service):
    with pytest.raises(NotFoundError):
        await service.list_owner_restaurants(uuid.uuid4(), PageParams(page=1, page_size=20))


async def test_restaurant_reservations_include_guest(service):
    day = date(2030, 1, 2)
    restaurant, rows, _ = await service.list_restaurant_reservations(1, day, PageParams(page=1, page_size=20))

    assert restaurant is RESTAURANT
    assert rows[0][2].name == "손님"
    assert service.query.received == (1, day, 0, 20)


async def test_unknown_restaurant_raises_not_found_before_query(service):
    with pytest.raises(NotFoundError):
        await service.list_restaurant_reservations(999, None, PageParams(page=1, page_size=20))

    assert service.query.received is None  # 없는 식당이면 예약 창고는 안 부름
