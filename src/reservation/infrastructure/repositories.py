# [담당 4] 예약 창고 주방 : reservations 표를 읽고 써서 Reservation으로 돌려줌, 트랜잭션 시간 제한 걸기
import uuid
from datetime import datetime, timedelta

from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from common.unit_of_work import ConflictError
from reservation.domain.repository import ReservationRepository
from reservation.domain.reservation import (
    CancelledBy,
    CancelReason,
    Reservation,
    ReservationStatus,
)
from reservation.infrastructure.models import ReservationModel
from reservation.infrastructure.time_limits import DEFAULT_TIME_LIMITS, TimeLimits
from restaurant.infrastructure.models import RestaurantModel
from slot.infrastructure.models import ReservationSlotModel


def to_reservation(model: ReservationModel) -> Reservation:
    """DB 표 한 줄(ReservationModel) -> 도메인 Reservation. 문자열로 저장한 상태·누가·왜를 다시 Enum으로 바꾼다."""
    return Reservation(
        id=model.id,
        user_id=model.user_id,
        slot_id=model.slot_id,
        party_size=model.party_size,
        contact_phone=model.contact_phone,
        status=ReservationStatus(model.status),
        created_at=model.created_at,
        cancelled_at=model.cancelled_at,
        cancelled_by=CancelledBy(model.cancelled_by) if model.cancelled_by else None,
        cancel_reason=CancelReason(model.cancel_reason)
        if model.cancel_reason
        else None,
        cancel_note=model.cancel_note,
        checked_in_at=model.checked_in_at,
    )


class SQLAlchemyReservationRepository(ReservationRepository):
    """ReservationRepository 약속을 SQLAlchemy로 구현. 세션은 밖(서비스)에서 받아 쓴다."""

    def __init__(
        self, session: AsyncSession, time_limits: TimeLimits = DEFAULT_TIME_LIMITS
    ) -> None:
        self.session = session
        self.time_limits = (
            time_limits  # 공장이 환경변수 값으로 넣어 줌 (없으면 3초·5초·10초)
        )

    async def set_time_limits(self) -> None:
        # set_config(이름, 값, true) = SET LOCAL : 이 트랜잭션에만 걸리고 commit/rollback하면 원래대로 돌아간다
        # (SET은 값 자리에 변수를 못 쓰지만 set_config는 쓸 수 있어서, 값이 SQL에 직접 섞이지 않는다)
        settings = self.time_limits.as_settings()
        await self.session.execute(
            text(
                "SELECT set_config('lock_timeout', :lock, true),"
                " set_config('statement_timeout', :statement, true),"
                " set_config('idle_in_transaction_session_timeout', :idle, true)"
            ),
            {
                "lock": settings["lock_timeout"],
                "statement": settings["statement_timeout"],
                "idle": settings["idle_in_transaction_session_timeout"],
            },
        )

    async def exists_confirmed(self, user_id: uuid.UUID, slot_id: int) -> bool:
        stmt = (
            select(ReservationModel.id)
            .where(
                ReservationModel.user_id == user_id,
                ReservationModel.slot_id == slot_id,
                ReservationModel.status
                == ReservationStatus.CONFIRMED.value,  # DB에는 문자열이라 .value로 비교
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
        try:
            await self.session.flush()
        except IntegrityError as e:
            # 확정 예약 부분 unique 인덱스에 걸리면 DB 말(IntegrityError)을 포트 약속 말(ConflictError)로 번역
            raise ConflictError() from e
        return to_reservation(model)

    async def get(self, reservation_id: int) -> Reservation | None:
        stmt = select(ReservationModel).where(ReservationModel.id == reservation_id)
        model = (await self.session.execute(stmt)).scalar_one_or_none()
        return to_reservation(model) if model else None

    async def get_for_update(self, reservation_id: int) -> Reservation | None:
        stmt = (
            select(ReservationModel)
            .where(ReservationModel.id == reservation_id)
            .with_for_update()  # 행 자물쇠. 앞 요청이 commit/rollback할 때까지 기다림 (두 번 취소 막기)
            .execution_options(
                populate_existing=True
            )  # 세션에 옛 값이 있어도 방금 읽은 값으로 덮어씀
        )
        model = (await self.session.execute(stmt)).scalar_one_or_none()
        return to_reservation(model) if model else None

    async def save(self, reservation: Reservation) -> None:
        model = await self.session.get(
            ReservationModel, reservation.id
        )  # get_for_update로 읽은 그 행을 세션에서 다시 꺼냄 (DB에 새로 묻지 않음)
        if model is None:
            raise LookupError(
                f"reservation {reservation.id} not loaded in this session"
            )
        model.status = reservation.status.value
        model.cancelled_at = reservation.cancelled_at
        model.cancelled_by = (
            reservation.cancelled_by.value if reservation.cancelled_by else None
        )
        model.cancel_reason = (
            reservation.cancel_reason.value if reservation.cancel_reason else None
        )
        model.cancel_note = reservation.cancel_note
        model.checked_in_at = reservation.checked_in_at
        await self.session.flush()  # 바뀐 값을 DB에 보냄. 확정(commit)은 서비스가 한다.

    async def restaurant_owner_of(self, reservation_id: int) -> uuid.UUID | None:
        # 예약 -> 슬롯 -> 식당을 한 번에 이어서 주인 id만 꺼낸다. 삭제된 식당은 없는 것으로 본다
        stmt = (
            select(RestaurantModel.owner_id)
            .select_from(ReservationModel)
            .join(
                ReservationSlotModel,
                ReservationSlotModel.id == ReservationModel.slot_id,
            )
            .join(
                RestaurantModel,
                RestaurantModel.id == ReservationSlotModel.restaurant_id,
            )
            .where(
                ReservationModel.id == reservation_id,
                RestaurantModel.deleted_at.is_(None),
            )
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def list_no_show_ids(self, now: datetime, grace: timedelta) -> list[int]:
        # 확정 + 입장 안 함 + 시작 시각이 (지금 - 유예 시간) 이하인 예약 = 노쇼 대상
        stmt = (
            select(ReservationModel.id)
            .join(
                ReservationSlotModel,
                ReservationSlotModel.id == ReservationModel.slot_id,
            )
            .where(
                ReservationModel.status == ReservationStatus.CONFIRMED.value,
                ReservationModel.checked_in_at.is_(None),
                ReservationSlotModel.starts_at <= now - grace,
            )
            .order_by(ReservationModel.id)
        )
        return list((await self.session.execute(stmt)).scalars().all())
