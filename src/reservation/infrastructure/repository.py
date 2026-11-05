from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from reservation.domain.reservation import Reservation, ReservationStatus
from reservation.domain.repository import ReservationRepository
from reservation.infrastructure.models import ReservationModel

def to_reservation(model):
    return Reservation(
        id=model.id,
        user_id=model.user_id,
        slot_id=model.slot_id,
        party_size=model.party_size,
        contact_phone=model.contact_phone,
        status=ReservationStatus(model.status),
        created_at=model.created_at,
        cancelled_at=model.cancelled_at
    )

class SQLAlchemyReservationRepository(ReservationRepository):
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, reservation_id: int) -> Reservation | None:
        stmt = select(ReservationModel).where(ReservationModel.id == reservation_id)
        model = (await self.session.execute(stmt)).scalar_one_or_none()
        return to_reservation(model) if model else None