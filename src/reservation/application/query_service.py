# [담당 5] 예약 조회 매니저: 일 순서 정하기
from sqlalchemy.ext.asyncio import AsyncSession

from auth.domain.value_object import AuthenticatedUser  # 담당 1: 로그인한 사람
from common.errors import NotFoundError  # 담당 2: 404 오류
from common.pagination import PageParams  # 담당 2: 페이지 정보
from reservation.domain.reservation import ReservationStatus  # 담당 4: 예약 상태
from reservation.infrastructure.query_repository import ReservationQueryRepository  # 담당 5: 창고


class ReservationQueryService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.query = ReservationQueryRepository(db)

    async def list_my_reservations(self, me: AuthenticatedUser, status: ReservationStatus | None, page: PageParams):
        # 창고에 "이 사람 예약 꺼내 와" 시키기
        return await self.query.list_my_reservations(me.user_id, status, page.offset, page.page_size)

    # 5단계: 예약 상세. 본인이나 그 식당 운영자만, 나머지는 404로 숨기기
    async def get_reservation(self, me: AuthenticatedUser, reservation_id: int):
        reservation, slot, _ = await self.get_reservation_with_owner(me, reservation_id)
        return reservation, slot

    # 예약 상세 + 식당 주인 id (담당 4: 상세 화면의 can_cancel이 운영자 버튼을 판단할 때 씀)
    async def get_reservation_with_owner(self, me: AuthenticatedUser, reservation_id: int):
        # 1. 창고에서 꺼내기. 없으면 404
        found = await self.query.get_reservation(reservation_id)
        if found is None:
            raise NotFoundError()

        reservation, slot, owner_id = found

        # 2. 내 예약인가? 내 식당인가?
        is_mine = reservation.user_id == me.user_id
        is_my_restaurant = owner_id == me.user_id

        # 3. 둘 다 아니면 404 (403 아님: 있는지조차 숨기기). 관리자는 모든 예약 상세를 볼 수 있다 (취소도 가능해서)
        if not (is_mine or is_my_restaurant or me.is_admin()):
            raise NotFoundError()

        return reservation, slot, owner_id
