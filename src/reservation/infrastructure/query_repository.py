# [담당 5] 예약조회 창고: DB에서 꺼내기
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from reservation.domain.reservation import Reservation, ReservationStatus  # 담당 4: 예약
from reservation.infrastructure.models import ReservationModel  # 담당 4: 예약 표(DB)
from reservation.infrastructure.repositories import to_reservation # 담당4 표->예약
from slot.infrastructure.repository import to_time_slot # 담당3: 표->슬롯
from slot.domain.time_slot import TimeSlot  # 담당 3: 슬롯
from slot.infrastructure.models import ReservationSlotModel  # 담당 3: 슬롯 표(DB) (아직 없음)
from restaurant.infrastructure.models import RestaurantModel  # 담당 2: 식당 표(DB) (아직 없음)


class ReservationQueryRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_my_reservations(
        self, user_id: uuid.UUID, status: ReservationStatus | None, offset: int, limit: int
    ) -> tuple[list[tuple[Reservation, TimeSlot]], int]:
        conditions = [ReservationModel.user_id == user_id]
        if status is not None:
            conditions += [ReservationModel.status == status]

        joined = select(ReservationModel, ReservationSlotModel).join(
            ReservationSlotModel, ReservationSlotModel.id == ReservationModel.slot_id
        )

        total = await self.db.scalar(select(func.count()).select_from(ReservationModel).where(*conditions))

        rows = await self.db.execute(
            joined.where(*conditions)
            .order_by(ReservationSlotModel.starts_at.desc(), ReservationModel.id.desc())  # 같은 시각이면 최근 예약 먼저
            .offset(offset)
            .limit(limit)
        )

        return [(to_reservation(r), to_time_slot(s)) for r, s in rows], total or 0

    # 5단계: 예약 하나 + 슬롯 + 그 식당 주인 번호
    async def get_reservation(self, reservation_id: int) -> tuple[Reservation, TimeSlot, uuid.UUID] | None:
        result = await self.db.execute(
            select(ReservationModel, ReservationSlotModel, RestaurantModel.owner_id)
            .join(ReservationSlotModel, ReservationSlotModel.id == ReservationModel.slot_id)
            .join(RestaurantModel, RestaurantModel.id == ReservationSlotModel.restaurant_id)
            .where(ReservationModel.id == reservation_id)
        )
        row = result.first()  # 한 줄만. 없으면 None

        if row is None:
            return None

        r, s, owner_id = row
        return to_reservation(r), to_time_slot(s), owner_id
