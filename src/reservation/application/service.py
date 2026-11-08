# [담당 4] 예약 매니저 : 예약 생성, 취소의 순서와 한 묶음 확정(트랜잭션)
import uuid
from datetime import datetime

from common.errors import NotFoundError
from common.unit_of_work import ConflictError, UnitOfWork
from reservation.domain.exceptions import DuplicateReservationError
from reservation.domain.repository import ReservationRepository
from reservation.domain.reservation import Reservation
from slot.domain.repository import SlotRepository
from slot.domain.time_slot import TimeSlot


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
        try:
            saved = await self.reservation_repo.add(reservation)
        except ConflictError:
            # 2번 확인을 지나친 중복을 DB 규칙(확정 예약은 사람·슬롯당 하나)이 막은 경우. DB는 저장(add)하는 순간 검사한다
            raise DuplicateReservationError()
        await self.slot_repo.save(slot)

        # 5. 맨 끝에 한 번만 확정한다. 슬롯 잠금도 여기서 풀린다.
        await self.uow.commit()
        return saved, slot

    async def cancel(
        self,
        user_id: uuid.UUID,
        reservation_id: int,
        now: datetime,
    ) -> tuple[Reservation, TimeSlot]:
        """예약을 취소한다. 확인 -> 슬롯 잠금 -> 예약 잠금 -> 취소 -> 자리 반납 -> 저장 -> commit (한 묶음)"""
        # 1. 잠그기 전에 먼저 꺼내서, 어느 슬롯인지 알아내고 내 예약인지 확인한다. 아니면 404
        found = await self.reservation_repo.get(reservation_id)
        if found is None or found.user_id != user_id:
            raise NotFoundError()

        # 2. 생성과 같은 순서로 잠근다: 슬롯 -> 예약 (순서가 같아야 데드락이 안 생긴다.)
        slot = await self.slot_repo.get_for_update(found.slot_id)
        if slot is None:
            raise NotFoundError()
        reservation = await self.reservation_repo.get_for_update(reservation_id)
        if reservation is None:
            raise NotFoundError()

        # 3. 잠근 뒤 읽은 최신 상태로 취소한다. 이미 취소됨, 시작됨이면 도메인이 409 에러를 낸다.
        reservation.cancel(slot_starts_at=slot.starts_at, now=now)

        # 4. 자리를 반납하고, 바뀐 예약과 슬롯을 저장한다.
        slot.release(reservation.party_size)
        await self.reservation_repo.save(reservation)
        await self.slot_repo.save(slot)

        # 5. 맨 끝에 한 번만 확정한다. 두 잠금도 여기서 풀린다.
        await self.uow.commit()
        return reservation, slot
