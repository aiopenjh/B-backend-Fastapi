# [담당 4] 예약 매니저 : 예약 생성, 취소의 순서와 한 묶음 확정(트랜잭션)
import uuid
from datetime import datetime

from common.errors import NotFoundError
from reservation.domain.exceptions import DuplicateReservationError
from reservation.domain.repository import ReservationRepository
from reservation.domain.reservation import Reservation
from slot.domain.repository import SlotRepository
from slot.domain.time_slot import TimeSlot
from common.unit_of_work import UnitOfWork


class ReservationService:
    """예약을 만들고 취소한다. 저장소에 일을 시키고, 맨 끝에 한 번만 commit한다."""

    def __init__(
        self,
        reservation_repo: ReservationRepository,
        slot_repo: SlotRepository,
        uow: UnitOfWork,
    ) -> None:
        self.reservation_repo = reservation_repo
        self.slot_repo = slot_repo
        self.uow = uow

    async def create(
        self,
        user_id: uuid.UUID,
        slot_id: int,
        party_size: int,
        contact_phone: str | None,
        now: datetime,
    ) -> tuple[Reservation, TimeSlot]:
        """예약을 만든다. 슬롯 잠금 -> 중복 확인 -> 자리 늘리기 -> 저장 -> commit (한 묶음)."""
        # 1. 슬롯을 잠그고 꺼낸다. 없으면 404
        slot = await self.slot_repo.get_for_update(slot_id)
        if slot is None:
            raise NotFoundError()

        # 2. 같은 슬롯에 내 확정 예약이 이미 있으면 409
        if await self.reservation_repo.exists_confirmed(user_id, slot_id):
            raise DuplicateReservationError()

        # 3. 자리 늘리기. 시작됨, 인원 초과, 자리 부족이면 TimeSlot이 409 에러를 낸다.
        slot.reserve(party_size, now)

        # 4. 예약을 만들어 저장하고, 바뀐 슬롯도 저장한다
        reservation = Reservation.create(
            user_id=user_id,
            slot_id=slot_id,
            party_size=party_size,
            now=now,
            contact_phone=contact_phone,
        )
        saved = await self.reservation_repo.add(reservation)
        await self.slot_repo.save(slot)

        # 5. 맨 끝에 한 번만 확정한다. 슬롯 잠금도 여기서 풀린다.
        await self.uow.commit()
        return saved, slot
