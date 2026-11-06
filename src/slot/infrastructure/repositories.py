# [담당3-영민] SQLAlchemy 구현체 - ORM 모델
from datetime import datetime

from sqlalchemy import column, select, table
from sqlalchemy.ext.asyncio import AsyncSession

from slot.domain.repository import SlotRepository
from slot.domain.time_slot import TimeSlot
from slot.infrastructure.models import ReservationSlotModel

# [담당2-김태양] restaurant.application 조회 함수 생기면 아래 줄 삭제
_restaurants = table("restaurants", column("id"), column("deleted_at"))


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
        """ 현재, 임시. 식당 모듈 조회 기능으로 대체 [담당2-김태양]"""
        stmt = select(_restaurants.c.id).where(
            _restaurants.c.id == restaurant_id,
            _restaurants.c.deleted_at.is_(None),
        )
        return (await self.session.execute(stmt)).first() is not None
