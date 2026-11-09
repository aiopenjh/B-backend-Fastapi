# [담당 5] 손님 둘러보기 매니저: 지역 칩 목록, 지역별 식당 (읽기 전용)
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

    async def list_regions(self) -> list[tuple[str, int]]:
        return await self.query.list_regions()

    async def list_region_restaurants(
        self, region: str, q: str | None, cuisine: str | None, sort: str, page: PageParams
    ) -> tuple[list[Restaurant], int]:
        return await self.query.list_restaurants(region, q, cuisine, sort, page.offset, page.page_size)
