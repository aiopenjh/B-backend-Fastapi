# [담당 5] 운영자 매니저: 일 순서 정하기
from datetime import date
from sqlalchemy.ext.asyncio import AsyncSession

from common.pagination import PageParams  # 담당 2: 페이지 정보
from common.errors import ForbiddenError, NotFoundError  # 담당 2: 403 · 404 오류
from owner.infrastructure.query_repository import OwnerQueryRepository  # 담당 5: 창고
from restaurant.domain.restaurant import Restaurant  # 담당 2: 식당
from auth.domain.value_object import AuthenticatedUser  # 담당 1: 회원


class OwnerService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.query = OwnerQueryRepository(db)

    async def list_my_restaurants(self, owner: AuthenticatedUser, page: PageParams) -> tuple[list[Restaurant], int]:
        return await self.query.list_restaurants(owner.user_id, page.offset, page.page_size)

    async def list_restaurant_reservations(
        self, owner: AuthenticatedUser, restaurant_id: int, day: date | None, page: PageParams
    ):
        # 1. 식당이 있나?
        restaurant = await self.query.get_restaurant(restaurant_id)
        if restaurant is None:
            raise NotFoundError()       # 404

        # 2. 내 식당인가?
        if not restaurant.is_owned_by(owner.user_id):
            raise ForbiddenError()      # 403

        # 3. 창고에 예약 목록 시키기
        return await self.query.list_reservations(restaurant_id, day, page.offset, page.page_size)

    async def export_restaurant_reservations(
        self, owner: AuthenticatedUser, restaurant_id: int, day: date | None
    ):
        restaurant = await self.query.get_restaurant(restaurant_id)
        if restaurant is None:
            raise NotFoundError()       # 404

        if not restaurant.is_owned_by(owner.user_id):
            raise ForbiddenError()      # 403

        return await self.query.list_all_reservations(restaurant_id, day)