from common.pagination import PageParams
from restaurant.domain.exceptions import RestaurantNotFoundError
from restaurant.domain.restaurant import Restaurant
from restaurant.infrastructure.repository import RestaurantRepository


class RestaurantService:
    def __init__(self, repo: RestaurantRepository):
        self.repo = repo

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
