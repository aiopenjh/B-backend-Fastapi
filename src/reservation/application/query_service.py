# [담당 5] 예약 조회 매니저: 일 순서 정하기
from sqlalchemy.ext.asyncio import AsyncSession

from auth.domain.value_object import AuthenticatedUser  # 담당 1: 로그인한 사람
from common.pagination import PageParams  # 담당 2: 페이지 정보 (아직 없음)
from reservation.domain.reservation import ReservationStatus  # 담당 4: 예약 상태
from reservation.infrastructure.query_repository import ReservationQueryRepository  # 담당 5: 창고


class ReservationQueryService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.query = ReservationQueryRepository(db)

    async def list_my_reservations(self, me: AuthenticatedUser, status: ReservationStatus | None, page: PageParams):
        # 창고에 "이 사람 예약 꺼내 와" 시키기
        return await self.query.list_my_reservations(me.user_id, status, page.offset, page.page_size)
