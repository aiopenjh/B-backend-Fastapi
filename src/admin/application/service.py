# [담당 5] 관리자 매니저: 일 순서 정하기 (읽기 전용, 관리자 확인은 화면 문지기가 함)
import uuid
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from admin.infrastructure.query_repository import (  # 담당 5: 관리자 창고
    AdminQueryRepository,
    Guest,
)
from common.errors import NotFoundError  # 담당 2: 404 오류
from common.pagination import PageParams  # 담당 2: 페이지 정보
from owner.infrastructure.query_repository import (
    OwnerQueryRepository,  # 담당 5: 운영자 창고 (재사용)
)
from reservation.domain.reservation import Reservation  # 담당 4: 예약
from restaurant.domain.restaurant import Restaurant  # 담당 2: 식당
from slot.domain.time_slot import TimeSlot  # 담당 3: 슬롯
from user.domain.user import User  # 담당 1: 회원


class AdminService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.query = AdminQueryRepository(db)
        self.restaurants = OwnerQueryRepository(db)  # 식당 하나·운영자별 식당 목록은 운영자 창고 그대로

    async def list_owners(self, page: PageParams) -> tuple[list[tuple[User, int]], int]:
        # 운영자 목록 + 식당 수
        return await self.query.list_owners(page.offset, page.page_size)

    async def list_owner_restaurants(
        self, owner_id: uuid.UUID, page: PageParams
    ) -> tuple[User, list[Restaurant], int]:
        # 1. 운영자가 있나? (없거나 운영자가 아니면 404)
        owner = await self.query.get_owner(owner_id)
        if owner is None:
            raise NotFoundError()

        # 2. 그 운영자의 식당 목록 (운영자 창고 재사용)
        items, total = await self.restaurants.list_restaurants(owner_id, page.offset, page.page_size)
        return owner, items, total

    async def list_restaurant_reservations(
        self, restaurant_id: int, day: date | None, page: PageParams
    ) -> tuple[Restaurant, list[tuple[Reservation, TimeSlot, Guest]], int]:
        # 1. 식당이 있나? (없거나 지운 식당이면 404). 관리자는 모든 식당을 보므로 "내 식당인가"는 확인하지 않음
        restaurant = await self.restaurants.get_restaurant(restaurant_id)
        if restaurant is None:
            raise NotFoundError()

        # 2. 예약 + 예약자 이름
        rows, total = await self.query.list_reservations(restaurant_id, day, page.offset, page.page_size)
        return restaurant, rows, total
