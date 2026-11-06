# [담당3-영민] SQLAlchemy 구현체 - ORM 모델
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from restaurant.infrastructure.repository import RestaurantRepository
from slot.domain.repository import SlotRepository
from slot.domain.time_slot import TimeSlot
from slot.infrastructure.models import ReservationSlotModel


# 외부 사용 중 — owner·reservation query_repository (#27). 이름·인자 바꾸면 담당 5와 함께
def _to_domain(row: ReservationSlotModel) -> TimeSlot:
    return TimeSlot(
        id=row.id,
        restaurant_id=row.restaurant_id,
        starts_at=row.starts_at,
        ends_at=row.ends_at,
        capacity=row.capacity,
        reserved_guests=row.reserved_guests,
        max_party_size=row.max_party_size,
    )

class SQLAlchemySlotRepository(SlotRepository):
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_for_day(self, restaurant_id: int, start: datetime, end: datetime) -> list[TimeSlot]:
        stmt = (
            select(ReservationSlotModel)
            .where(
                ReservationSlotModel.restaurant_id == restaurant_id,
                ReservationSlotModel.starts_at >= start,
                ReservationSlotModel.starts_at < end,
            )
            .order_by(ReservationSlotModel.starts_at)
        )
        rows = (await self.session.execute(stmt)).scalars().all()
        return [_to_domain(r) for r in rows]

    async def get_for_update(self, slot_id: int) -> TimeSlot | None:
        stmt = (
            select(ReservationSlotModel)
            .where(ReservationSlotModel.id == slot_id)
            .with_for_update()
        )
        row = (await self.session.execute(stmt)).scalar_one_or_none()
        return _to_domain(row) if row else None

    async def save(self, slot: TimeSlot) -> None:
        row = await self.session.get(ReservationSlotModel, slot.id)
        if row is None:
            raise LookupError(f"slot {slot.id} not loaded in this session")
        row.reserved_guests = slot.reserved_guests
        await self.session.flush()

    async def restaurant_exists(self, restaurant_id: int) -> bool:
        """[담당2-김태양] RestaurantRepository에 위임"""
        return await RestaurantRepository(self.session).find_by_id(restaurant_id) is not None
        # RestaurantRepository(self.session)은 식당 모델을 조회하는 메서드를 가지고 있음
        # find_by_id(restaurant_id)는 식당 모델을 조회하는 메서드