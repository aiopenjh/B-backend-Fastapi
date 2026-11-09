# [담당 5] 손님 둘러보기 창고: 지역(구) 목록, 지역별 식당 꺼내기 (읽기 전용)
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from restaurant.domain.restaurant import Restaurant  # 담당 2: 식당
from restaurant.infrastructure.models import RestaurantModel  # 담당 2: 식당 표(DB)
from restaurant.infrastructure.repository import (  # 담당 2: 정렬 칸, 표 → 식당
    SORT_COLUMNS,
    to_restaurant,
)

# 주소의 두 번째 단어가 구: "서울 중구 …", "서울특별시 종로구 …" → 중구, 종로구
REGION = func.split_part(RestaurantModel.address, " ", 2)


class BrowseQueryRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_regions(self) -> list[tuple[str, int]]:
        """지역(구)과 식당 수. 지운 식당은 빼고, 가나다순"""
        rows = await self.db.execute(
            select(REGION, func.count())
            .where(RestaurantModel.deleted_at.is_(None))
            .group_by(REGION)
            .order_by(REGION.collate("C"))  # 글자 번호 순 = 한글 가나다순
        )
        return [(region, count) for region, count in rows if region]

    async def list_restaurants(
        self, region: str, q: str | None, cuisine: str | None, sort: str, offset: int, limit: int
    ) -> tuple[list[Restaurant], int]:
        """한 지역의 식당 목록과 전체 개수 (검색·음식 종류·정렬은 식당 목록과 같은 규칙)"""
        conditions = [RestaurantModel.deleted_at.is_(None), REGION == region]
        if q:
            conditions.append(RestaurantModel.name.icontains(q, autoescape=True))
        if cuisine:
            conditions.append(RestaurantModel.cuisine == cuisine)

        total = await self.db.scalar(select(func.count()).select_from(RestaurantModel).where(*conditions))
        models = await self.db.scalars(
            select(RestaurantModel)
            .where(*conditions)
            .order_by(*SORT_COLUMNS.get(sort, SORT_COLUMNS["id"]))
            .offset(offset)
            .limit(limit)
        )
        return [to_restaurant(m) for m in models], total or 0
