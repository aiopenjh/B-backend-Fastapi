# [담당 5] 운영자 창고: DB에서 꺼내기

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from restaurant.domain.restaurant import Restaurant  # 담당 2: 식당
from restaurant.infrastructure.models import RestaurantModel  # 담당 2: 식당 표(DB)
from restaurant.infrastructure.repository import to_restaurant  # 담당 2: 표 → 식당


class OwnerQueryRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_restaurants(self, owner_id: int, offset: int, limit: int) -> tuple[list[Restaurant], int]:
        conditions = [RestaurantModel.owner_id == owner_id, RestaurantModel.deleted_at.is_(None)]
        total = await self.db.scalar(select(func.count()).select_from(RestaurantModel).where(*conditions))
        rows = await self.db.scalars(
            select(RestaurantModel).where(*conditions).order_by(RestaurantModel.id).offset(offset).limit(limit)
        )
        return [to_restaurant(m) for m in rows], total or 0