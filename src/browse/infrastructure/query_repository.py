# [담당 5] 손님 둘러보기 창고: 지역(구 → 동)과 음식 종류로 식당 꺼내기 (읽기 전용)
from datetime import date, datetime

from sqlalchemy import String, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from restaurant.domain.restaurant import Restaurant  # 담당 2: 식당
from restaurant.infrastructure.models import RestaurantModel  # 담당 2: 식당 표(DB)
from restaurant.infrastructure.repository import to_restaurant  # 담당 2: 표 → 식당
from slot.domain.day_range import SEOUL  # 담당 3: 서울 시간대
from slot.infrastructure.models import ReservationSlotModel  # 담당 3: 슬롯 표(DB)

# 주소 두 번째 단어 = 구 ("서울특별시 종로구 수표로 146 (낙원동)" → 종로구)
DISTRICT = func.split_part(RestaurantModel.address, " ", 2)
# 주소 끝 괄호 안 첫 낱말 = 동 ("(낙원동)", "(관철동, ○○빌딩)" → 낙원동, 관철동). 괄호가 없으면 NULL
DONG = func.trim(func.substring(RestaurantModel.address, r"\(([^,)]+)"))
ACTIVE = RestaurantModel.deleted_at.is_(None)


class BrowseQueryRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_districts(self) -> list[str]:
        """식당이 있는 구 (가나다순)"""
        rows = await self.db.scalars(
            select(DISTRICT).where(ACTIVE).group_by(DISTRICT).order_by(DISTRICT.collate("C"))
        )
        return [name for name in rows if name]

    async def list_dongs(self, district: str) -> list[str]:
        """한 구 안에서 식당이 있는 동 (가나다순, 주소에 동이 없는 식당은 빠짐)"""
        rows = await self.db.scalars(
            select(DONG)
            .where(ACTIVE, DISTRICT == district, DONG.is_not(None))
            .group_by(DONG)
            .order_by(DONG.collate("C"))
        )
        return [name for name in rows if name]

    async def list_cuisines(self) -> list[str]:
        """식당이 있는 음식 종류 (가나다순)"""
        rows = await self.db.scalars(
            select(RestaurantModel.cuisine)
            .where(ACTIVE)
            .group_by(RestaurantModel.cuisine)
            .order_by(RestaurantModel.cuisine.collate("C"))
        )
        return list(rows)

    async def list_restaurants(
        self,
        district: str | None,
        dong: str | None,
        q: str | None,
        cuisine: str | None,
        seed: str,
        offset: int,
        limit: int,
    ) -> tuple[list[Restaurant], int]:
        """식당 목록과 전체 개수. 구(와 동)를 고르면 그 지역만. 순서는 seed로 섞음"""
        conditions = [ACTIVE]
        if district:
            conditions.append(DISTRICT == district)
            if dong:
                conditions.append(DONG == dong)
        if q:
            conditions.append(RestaurantModel.name.icontains(q, autoescape=True))
        if cuisine:
            conditions.append(RestaurantModel.cuisine == cuisine)

        total = await self.db.scalar(select(func.count()).select_from(RestaurantModel).where(*conditions))
        models = await self.db.scalars(
            select(RestaurantModel)
            .where(*conditions)
            # 같은 seed면 같은 순서 (페이지를 넘겨도 겹치지 않음), seed가 바뀌면 새로 섞임
            .order_by(func.md5(cast(RestaurantModel.id, String) + seed), RestaurantModel.id)
            .offset(offset)
            .limit(limit)
        )
        return [to_restaurant(m) for m in models], total or 0

    async def next_open_day(self, restaurant_id: int, after: datetime) -> date | None:
        """지금 이후 자리가 남은 가장 가까운 시간대의 날짜(서울). 없으면 None"""
        starts_at = await self.db.scalar(
            select(func.min(ReservationSlotModel.starts_at)).where(
                ReservationSlotModel.restaurant_id == restaurant_id,
                ReservationSlotModel.starts_at > after,
                ReservationSlotModel.reserved_guests < ReservationSlotModel.capacity,
            )
        )
        return starts_at.astimezone(SEOUL).date() if starts_at else None
