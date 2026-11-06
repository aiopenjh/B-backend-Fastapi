# [담당 4] 예약 창고 주방 : reservations 표를 읽고 써서 Reservation으로 돌려줌
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from reservation.domain.repository import ReservationRepository
from reservation.domain.reservation import Reservation, ReservationStatus
from reservation.infrastructure.models import ReservationModel


def to_reservation(model: ReservationModel) -> Reservation:
    return Reservation(
        id=model.id,
        user_id=model.user_id,
        slot_id=model.slot_id,
        party_size=model.party_size,
        contact_phone=model.contact_phone,
        status=ReservationStatus(model.status),
        created_at=model.created_at,
        cancelled_at=model.cancelled_at,
    )


class SQLAlchemyReservationRepository(ReservationRepository):
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def exists_confirmed(self, user_id: uuid.UUID, slot_id: int) -> bool:
        stmt = (
            select(ReservationModel.id)
            .where(
                ReservationModel.user_id == user_id,
                ReservationModel.slot_id == slot_id,
                ReservationModel.status == ReservationStatus.CONFIRMED.value,
            )
            .limit(1)
        )
        found = (await self.session.execute(stmt)).scalar_one_or_none()
        return found is not None

    async def add(self, reservation: Reservation) -> Reservation:
        model = ReservationModel(
            user_id=reservation.user_id,
            slot_id=reservation.slot_id,
            party_size=reservation.party_size,
            contact_phone=reservation.contact_phone,
            status=reservation.status.value,
            created_at=reservation.created_at,
            cancelled_at=reservation.cancelled_at,
        )
        self.session.add(model)
        await self.session.flush()
        return to_reservation(model)

    async def get(self, reservation_id: int) -> Reservation | None:
        stmt = select(ReservationModel).where(ReservationModel.id == reservation_id)
        model = (await self.session.execute(stmt)).scalar_one_or_none()
        return to_reservation(model) if model else None

    async def get_for_update(self, reservation_id: int) -> Reservation | None:
        stmt = (
            select(ReservationModel)
            .where(ReservationModel.id == reservation_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        model = (await self.session.execute(stmt)).scalar_one_or_none()
        return to_reservation(model) if model else None

    async def save(self, reservation: Reservation) -> None:
        model = await self.session.get(ReservationModel, reservation.id)
        if model is None:
            raise LookupError(f"reservation {reservation.id} not loaded in this session")
        model.status = reservation.status.value
        model.cancelled_at = reservation.cancelled_at
        await self.session.flush()