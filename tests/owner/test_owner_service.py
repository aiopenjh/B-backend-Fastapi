# [담당 5 최지훈] 운영자 매니저 테스트: 404,403 판단 확인
import uuid

import pytest

from auth.domain.value_object import AuthenticatedUser, AuthRole # 담당1 로그인 한사람
from common.errors import ForbiddenError, NotFoundError # 공통오류
from common.pagination import PageParams # 담당2 페이지 정보
from owner.application.service import OwnerService # 담당5 시험할 매니저
from restaurant.domain.restaurant import Restaurant # 담당2 식당

OWNER_A = AuthenticatedUser(user_id=uuid.uuid4(), role=AuthRole.OWNER)
OWNER_B = AuthenticatedUser(user_id=uuid.uuid4(), role=AuthRole.OWNER)

RESTAURANT = Restaurant(
    id = 1,
    owner_id = OWNER_A.user_id,
    name = "테스트 식당",
    address = "서울시 구로구",
    cuisine = "KOREAN",
)

class FakeOwnerQueryRepository:
    """DB 없이 정해 진 값만 돌려주는 가짜 창고"""
    async def get_restaurant(self, restaurant_id): # 1번이면 RESTAURANT, 아니면 NONE
        if restaurant_id == RESTAURANT.id:
            return RESTAURANT
        return None

    async def list_reservations(self, restaurant_id, day, offset, limit):
        return [], 0 # 예약없음 전체, 0건
    
    async def list_all_reservations(self, restaurant_id, day):
        return [] # 예약목록만


async def test_owner_can_see_own_restaurant_reservations(): # 내식당 예약목록 확인 통과
    service = OwnerService(db=None)
    service.query = FakeOwnerQueryRepository()

    items, total = await service.list_restaurant_reservations(
        OWNER_A,
        RESTAURANT.id,
        None,
        PageParams(page=1, page_size=40),
    )
    assert items == []
    assert total == 0

async def test_other_owner_gets_403(): # 남의식당 예약목록 확인 403
    service = OwnerService(db=None)
    service.query = FakeOwnerQueryRepository()

    with pytest.raises(ForbiddenError):
        await service.list_restaurant_reservations(
            OWNER_B,
            RESTAURANT.id,
            None,
            PageParams(page=1, page_size=40),
        )

async def test_missing_restaurant_gets_404(): # 없는식당 예약목록 확인 404
    service = OwnerService(db=None)
    service.query = FakeOwnerQueryRepository()

    with pytest.raises(NotFoundError):
        await service.list_restaurant_reservations(
            OWNER_A,
            555,
            None,
            PageParams(page=1, page_size=40),
        )

async def test_other_owner_cannot_export_csv(): # 남의식당 csv 확인 403
    service = OwnerService(db=None)
    service.query = FakeOwnerQueryRepository()

    with pytest.raises(ForbiddenError):
        await service.export_restaurant_reservations(
            OWNER_B,
            RESTAURANT.id,
            None,
        )