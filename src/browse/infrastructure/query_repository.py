# [담당 5] 손님 둘러보기 창고: 지역(시·도 → 구·시·군)과 음식 종류로 식당 꺼내기 (읽기 전용)
from sqlalchemy import String, case, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from restaurant.domain.restaurant import Restaurant  # 담당 2: 식당
from restaurant.infrastructure.models import RestaurantModel  # 담당 2: 식당 표(DB)
from restaurant.infrastructure.repository import to_restaurant  # 담당 2: 표 → 식당

# 17개 시·도 정식 이름과 주소에 쓰이는 줄임말
PROVINCES = {
    "서울특별시": ["서울"],
    "부산광역시": ["부산"],
    "대구광역시": ["대구"],
    "인천광역시": ["인천"],
    "광주광역시": ["광주"],
    "대전광역시": ["대전"],
    "울산광역시": ["울산"],
    "세종특별자치시": ["세종"],
    "경기도": ["경기"],
    "강원특별자치도": ["강원도", "강원"],
    "충청북도": ["충북"],
    "충청남도": ["충남"],
    "전북특별자치도": ["전라북도", "전북"],
    "전라남도": ["전남"],
    "경상북도": ["경북"],
    "경상남도": ["경남"],
    "제주특별자치도": ["제주도", "제주"],
}

# 주소 첫 단어 = 시·도 (줄임말은 정식 이름으로), 두 번째 단어 = 구·시·군
FIRST_WORD = func.split_part(RestaurantModel.address, " ", 1)
PROVINCE = case(
    *[(FIRST_WORD.in_([name, *aliases]), name) for name, aliases in PROVINCES.items()],
    else_=FIRST_WORD,
)
DISTRICT = func.split_part(RestaurantModel.address, " ", 2)
ACTIVE = RestaurantModel.deleted_at.is_(None)


class BrowseQueryRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_districts(self, province: str) -> list[str]:
        """한 시·도 안에서 식당이 있는 구·시·군 (가나다순)"""
        rows = await self.db.scalars(
            select(DISTRICT)
            .where(ACTIVE, PROVINCE == province)
            .group_by(DISTRICT)
            .order_by(DISTRICT.collate("C"))
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
        province: str | None,
        district: str | None,
        q: str | None,
        cuisine: str | None,
        seed: str,
        offset: int,
        limit: int,
    ) -> tuple[list[Restaurant], int]:
        """식당 목록과 전체 개수. 시·도(와 구)를 고르면 그 지역만. 순서는 seed로 섞음"""
        conditions = [ACTIVE]
        if province:
            conditions.append(PROVINCE == province)
            if district:
                conditions.append(DISTRICT == district)
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
