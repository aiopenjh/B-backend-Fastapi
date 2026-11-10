# [담당 5] 손님 둘러보기 매니저: 지역(구 → 동)·음식 종류 목록, 지역별 식당 (읽기 전용)
from datetime import date, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from browse.infrastructure.query_repository import (
    BrowseQueryRepository,  # 담당 5: 둘러보기 창고
)
from common.pagination import PageParams  # 담당 2: 페이지 정보
from restaurant.domain.restaurant import Restaurant  # 담당 2: 식당


class BrowseService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.query = BrowseQueryRepository(db)

    async def list_districts(self) -> list[str]:
        return await self.query.list_districts()

    async def list_dongs(self, district: str) -> list[str]:
        return await self.query.list_dongs(district)

    async def list_cuisines(self) -> list[str]:
        return await self.query.list_cuisines()

    async def list_restaurants(
        self,
        district: str | None,
        dong: str | None,
        q: str | None,
        cuisine: str | None,
        seed: str,
        page: PageParams,
    ) -> tuple[list[Restaurant], int]:
        return await self.query.list_restaurants(district, dong, q, cuisine, seed, page.offset, page.page_size)

    async def next_open_day(self, restaurant_id: int, after: datetime) -> date | None:
        return await self.query.next_open_day(restaurant_id, after)
