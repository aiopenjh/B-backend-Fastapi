from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from restaurant.domain.restaurant import Menu, Restaurant
from restaurant.infrastructure.models import MenuModel, RestaurantModel

# 정렬 화이트리스트: 허용한 값만 컬럼으로 바꿈. 이름이 같으면 id 순
SORT_COLUMNS = {
    "id": [RestaurantModel.id],
    "name": [RestaurantModel.name, RestaurantModel.id],
}


def to_menu(model: MenuModel) -> Menu:
    """메뉴 표(DB) -> 도메인 Menu"""
    return Menu(
        id=model.id,
        name=model.name,
        price=model.price,
        description=model.description,
    )


def to_restaurant(model: RestaurantModel) -> Restaurant:
    """식당 표(DB) -> 도메인 Restaurant (메뉴 포함)"""
    return Restaurant(
        id=model.id,
        owner_id=model.owner_id,
        name=model.name,
        address=model.address,
        cuisine=model.cuisine,
        description=model.description,
        image_url=model.image_url,
        phone=model.phone,
        deleted_at=model.deleted_at,
        menus=[to_menu(menu) for menu in model.menus],
    )


class RestaurantRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def find_by_id(self, restaurant_id: int) -> Restaurant | None:
        """식당 하나. 없거나 삭제된 식당이면 None"""
        stmt = select(RestaurantModel).where(
            RestaurantModel.id == restaurant_id,
            RestaurantModel.deleted_at.is_(None),
        )
        model = await self.session.scalar(stmt)
        if model is None:
            return None
        return to_restaurant(model)

    async def find_all(
        self,
        q: str | None,
        cuisine: str | None,
        sort: str,
        offset: int,
        limit: int,
    ) -> tuple[list[Restaurant], int]:
        """식당 목록과 전체 개수. 삭제된 식당은 빼고, 검색, 필터, 정렬, 페이지 적용"""
        conditions = [RestaurantModel.deleted_at.is_(None)]
        if q:
            conditions.append(RestaurantModel.name.icontains(q, autoescape=True))
        if cuisine:
            conditions.append(RestaurantModel.cuisine == cuisine)

        # 1) 전체 개수 (페이지와 상관 없이)
        count_stmt = (
            select(func.count()).select_from(RestaurantModel).where(*conditions)
        )
        total = await self.session.scalar(count_stmt)

        # 2) 이번 페이지의 식당들
        order_columns = SORT_COLUMNS.get(sort, SORT_COLUMNS["id"])
        stmt = (
            select(RestaurantModel)
            .where(*conditions)
            .order_by(*order_columns)
            .offset(offset)
            .limit(limit)
        )
        models = (await self.session.scalars(stmt)).all()
        return [to_restaurant(model) for model in models], total or 0

    async def update(self, restaurant_id: int, changes: dict) -> Restaurant:
        """보낸 칸만 바꿈. commit은 서비스에서 하고, 여기서는 flush까지"""
        model = await self.session.get(RestaurantModel, restaurant_id)
        for key, value in changes.items():
            setattr(model, key, value)
        await self.session.flush()
        return to_restaurant(model)

    async def add_menu(self, restaurant_id: int, fields: dict) -> Menu:
        """메뉴 하나 추가. id는 DB가 만들어줌 (flush까지)"""
        model = MenuModel(
            restaurant_id=restaurant_id,
            name=fields["name"],
            price=fields["price"],
            description=fields["description"],
        )
        self.session.add(model)
        await self.session.flush()
        return to_menu(model)

    async def update_menu(self, menu_id: int, changes: dict) -> Menu:
        """메뉴의 보낸 칸만 바꿈 (flush)"""
        model = await self.session.get(MenuModel, menu_id)
        for key, value in changes.items():
            setattr(model, key, value)
        await self.session.flush()
        return to_menu(model)

    async def delete_menu(self, menu_id: int) -> None:
        """메뉴 삭제. 소프트 삭제가 아니라 실제로 지움 (flush)"""
        model = await self.session.get(MenuModel, menu_id)
        await self.session.delete(model)
        await self.session.flush()
