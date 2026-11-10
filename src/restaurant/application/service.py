from auth.domain.value_object import AuthenticatedUser
from common.pagination import PageParams
from common.unit_of_work import UnitOfWork
from restaurant.domain.exceptions import (
    NotRestaurantOwnerError,
    RestaurantNotFoundError,
)
from restaurant.domain.restaurant import Menu, Restaurant
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

    async def _get_editable_restaurant(
        self, user: AuthenticatedUser, restaurant_id: int
    ) -> Restaurant:
        """수정할 식당 찾기. 없으면 404, 권한 없으면 403"""
        restaurant = await self.repo.find_by_id(restaurant_id)
        if restaurant is None:
            raise RestaurantNotFoundError()
        if not restaurant.can_be_edited_by(user):
            raise NotRestaurantOwnerError()
        return restaurant

    async def update_restaurant(
        self,
        user: AuthenticatedUser,
        restaurant_id: int,
        changes: dict,
    ) -> Restaurant:
        """식당 수정. 없으면 404, 권한 없으면 403, 수정 뒤 commit"""
        await self._get_editable_restaurant(user, restaurant_id)
        updated = await self.repo.update(restaurant_id, changes)
        await self.uow.commit()
        return updated

    async def add_menu(
        self, user: AuthenticatedUser, restaurant_id: int, fields: dict
    ) -> Menu:
        """메뉴 등록. 식당 404, 권한 403"""
        await self._get_editable_restaurant(user, restaurant_id)
        menu = await self.repo.add_menu(restaurant_id, fields)
        await self.uow.commit()
        return menu

    async def update_menu(
        self, user: AuthenticatedUser, restaurant_id: int, menu_id: int, changes: dict
    ) -> Menu:
        """메뉴 수정. 식당 404, 권한 403, 이 식당의 메뉴가 아니면 404"""
        restaurant = await self._get_editable_restaurant(user, restaurant_id)
        restaurant.find_menu(menu_id)
        menu = await self.repo.update_menu(menu_id, changes)
        await self.uow.commit()
        return menu

    async def delete_menu(
        self, user: AuthenticatedUser, restaurant_id: int, menu_id: int
    ) -> None:
        """메뉴 삭제. 식당 404, 권한 403, 이 식당의 메뉴가 아니면 404"""
        restaurant = await self._get_editable_restaurant(user, restaurant_id)
        restaurant.find_menu(menu_id)
        await self.repo.delete_menu(menu_id)
        await self.uow.commit()
