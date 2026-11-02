# [담당 5] 운영자 매니저: 일 순서 정하기

from sqlalchemy.ext.asyncio import AsyncSession

from common.pagination import PageParams  # 담당 2: 페이지 정보
from owner.infrastructure.query_repository import OwnerQueryRepository  # 담당 5: 창고 (곧 만듦)
from restaurant.domain.restaurant import Restaurant  # 담당 2: 식당
from user.domain.user import User  # 담당 1: 회원


class OwnerService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.query = OwnerQueryRepository(db)

    async def list_my_restaurants(self, owner: User, page: PageParams) -> tuple[list[Restaurant], int]:
        return await self.query.list_restaurants(owner.id, page.offset, page.page_size)