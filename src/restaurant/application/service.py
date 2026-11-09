from auth.domain.value_object import AuthenticatedUser
from common.pagination import PageParams
from common.unit_of_work import UnitOfWork
from restaurant.domain.exceptions import (
    NotRestaurantOwnerError,
    RestaurantNotFoundError,
)
from restaurant.domain.restaurant import Restaurant
from restaurant.infrastructure.repository import RestaurantRepository


class RestaurantService:
    def __init__(self, repo: RestaurantRepository, uow: UnitOfWork):
        self.repo = repo
        self.uow = uow

    async def list_restaurants(
        self,
        q: str | None,
        cuisine: str | None,
        sort: str,
        page: PageParams,
    ) -> tuple[list[Restaurant], int]:
        """식당 목록과 전체 개수"""
        return await self.repo.find_all(q, cuisine, sort, page.offset, page.page_size)

    async def get_restaurant(self, restaurant_id: int) -> Restaurant:
        """식당 하나. 없거나 삭제된 식당이면 404"""
        restaurant = await self.repo.find_by_id(restaurant_id)
        if restaurant is None:
            raise RestaurantNotFoundError()
        return restaurant

    async def update_restaurant(
        self,
        user: AuthenticatedUser,
        restaurant_id: int,
        changes: dict,
    ) -> Restaurant:
        """식당 수정. 없으면 404, 권한 없으면 403, 수정 뒤 commit"""
        restaurant = await self.repo.find_by_id(restaurant_id)
        if restaurant is None:
            raise RestaurantNotFoundError()
        if not restaurant.can_be_edited_by(user):
            raise NotRestaurantOwnerError()

        updated = await self.repo.update(restaurant_id, changes)
        await self.uow.commit()
        return updated
