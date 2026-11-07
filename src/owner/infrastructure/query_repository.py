# [담당 5] 운영자 창고: DB에서 꺼내기
import uuid
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from reservation.domain.reservation import Reservation  # 담당 4: 예약
from reservation.infrastructure.models import ReservationModel  # 담당 4: 예약 표(DB)
from reservation.infrastructure.repositories import to_reservation  # 담당 4: 표 → 예약
from restaurant.domain.restaurant import Restaurant  # 담당 2: 식당
from restaurant.infrastructure.models import RestaurantModel  # 담당 2: 식당 표(DB)
from restaurant.infrastructure.repository import to_restaurant  # 담당 2: 표 → 식당
from slot.domain.day_range import seoul_day_range  # 담당 3: 서울 기준 하루 범위
from slot.domain.time_slot import TimeSlot  # 담당 3: 슬롯
from slot.infrastructure.models import ReservationSlotModel  # 담당 3: 슬롯 표(DB)
from slot.infrastructure.repositories import _to_domain  # 담당 3: 표 → 슬롯


class OwnerQueryRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_restaurants(self, owner_id: uuid.UUID, offset: int, limit: int) -> tuple[list[Restaurant], int]:
        conditions = [RestaurantModel.owner_id == owner_id, RestaurantModel.deleted_at.is_(None)]
        total = await self.db.scalar(select(func.count()).select_from(RestaurantModel).where(*conditions))
        rows = await self.db.scalars(
            select(RestaurantModel).where(*conditions).order_by(RestaurantModel.id).offset(offset).limit(limit)
        )
        return [to_restaurant(m) for m in rows], total or 0

    async def get_restaurant(self, restaurant_id: int) -> Restaurant | None:
        # 삭제된 식당은 없는 식당과 같게 봄 → 매니저가 404
        model = await self.db.scalar(
            select(RestaurantModel).where(RestaurantModel.id == restaurant_id, RestaurantModel.deleted_at.is_(None))
        )
        return to_restaurant(model) if model else None

    async def list_reservations(
        self, restaurant_id: int, day: date | None, offset: int, limit: int
    ) -> tuple[list[tuple[Reservation, TimeSlot]], int]:
        # 예약 표에는 식당 번호가 없음 → 슬롯 표와 JOIN해서 슬롯의 restaurant_id로 거름
        conditions = [ReservationSlotModel.restaurant_id == restaurant_id]
        if day is not None:
            # 서울 기준 그날 00:00 ~ 다음 날 00:00에 시작하는 슬롯만
            start, end = seoul_day_range(day)
            conditions += [ReservationSlotModel.starts_at >= start, ReservationSlotModel.starts_at < end]
        joined = select(ReservationModel, ReservationSlotModel).join(
            ReservationSlotModel, ReservationSlotModel.id == ReservationModel.slot_id
        )
        total = await self.db.scalar(
            select(func.count())
            .select_from(ReservationModel)
            .join(ReservationSlotModel, ReservationSlotModel.id == ReservationModel.slot_id)
            .where(*conditions)
        )
        # 표 두 개를 같이 꺼내므로 scalars가 아니라 execute → 한 줄마다 (예약, 슬롯) 짝
        rows = await self.db.execute(
            joined.where(*conditions)
            .order_by(ReservationSlotModel.starts_at, ReservationModel.id)  # 이용 시작 시각 순
            .offset(offset)
            .limit(limit)
        )
        return [(to_reservation(r), _to_domain(s)) for r, s in rows], total or 0

    # CSV용: 페이지 안나누고 전부
    async def list_all_reservations(
        self, restaurant_id: int, day: date | None
    ) -> list[tuple[Reservation, TimeSlot]]:
        conditions = [ReservationSlotModel.restaurant_id == restaurant_id]
        if day is not None:
            start, end = seoul_day_range(day)
            conditions += [ReservationSlotModel.starts_at >= start, ReservationSlotModel.starts_at < end]
        joined = select(ReservationModel, ReservationSlotModel).join(
            ReservationSlotModel, ReservationSlotModel.id == ReservationModel.slot_id
        )
        rows = await self.db.execute(
            joined.where(*conditions)
            .order_by(ReservationSlotModel.starts_at, ReservationModel.id)
        )
        return [(to_reservation(r), _to_domain(s)) for r, s in rows]
