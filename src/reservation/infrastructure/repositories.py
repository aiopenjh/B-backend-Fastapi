# [담당 4] 예약 창고 주방 : reservations 표를 읽고 써서 Reservation으로 돌려줌
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from reservation.domain.repository import ReservationRepository
from reservation.domain.reservation import Reservation, ReservationStatus
from reservation.infrastructure.models import ReservationModel


def to_reservation(model: ReservationModel) -> Reservation:
    """DB 표 한 줄(ReservationModel) -> 도메인 Reservation. 상태값 문자열은 ReservationStatus로 바꾼다."""
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
    """ReservationRepository 약속을 SQLAlchemy로 구현. 세션은 밖(서비스)에서 받아 쓴다."""
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def exists_confirmed(self, user_id: uuid.UUID, slot_id: int) -> bool:
        stmt = (
            select(ReservationModel.id)
            .where(
                ReservationModel.user_id == user_id,
                ReservationModel.slot_id == slot_id,
                ReservationModel.status == ReservationStatus.CONFIRMED.value, # DB에는 문자열이라 .value로 비교
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
        # DB에 보내서 id를 받아 온다. 확정(commit)은 서비스가 한다.
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
            .with_for_update() # 행 자물쇠. 앞 요청이 commit/rollback할 때까지 기다림 (두 번 취소 막기)
            .execution_options(populate_existing=True) # 세션에 옛 값이 있어도 방금 읽은 값으로 덮어씀
        )
        model = (await self.session.execute(stmt)).scalar_one_or_none()
        return to_reservation(model) if model else None

    async def save(self, reservation: Reservation) -> None:
        model = await self.session.get(ReservationModel, reservation.id) # get_for_update로 읽은 그 행을 세션에서 다시 꺼냄 (DB에 새로 묻지 않음)
        if model is None:
            raise LookupError(f"reservation {reservation.id} not loaded in this session")
        model.status = reservation.status.value
        model.cancelled_at = reservation.cancelled_at
        await self.session.flush() # 바뀐 값을 DB에 보냄. 확정(commit)은 서비스가 한다.