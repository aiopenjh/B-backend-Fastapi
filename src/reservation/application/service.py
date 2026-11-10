# [담당 4] 예약 매니저 : 예약 생성, 취소(손님·운영자·관리자·자동 노쇼), 입장 확인의 순서와 한 묶음 확정(트랜잭션)
import uuid
from datetime import datetime, timedelta

from auth.domain.value_object import AuthenticatedUser
from common.errors import NotFoundError
from common.unit_of_work import ConflictError, UnitOfWork
from reservation.domain.exceptions import (
    AlreadyCancelledError,
    AlreadyCheckedInError,
    DuplicateReservationError,
    NoShowTooEarlyError,
)
from reservation.domain.repository import ReservationRepository
from reservation.domain.reservation import (
    DEFAULT_NO_SHOW_GRACE,
    CancelledBy,
    CancelReason,
    Reservation,
)
from slot.domain.repository import SlotRepository
from slot.domain.time_slot import TimeSlot


class ReservationService:
    """예약을 만들고 취소한다. 저장소에 일을 시키고, 맨 끝에 한 번만 commit한다."""

    def __init__(
        self,
        reservation_repo: ReservationRepository,
        slot_repo: SlotRepository,
        uow: UnitOfWork,
        no_show_grace: timedelta = DEFAULT_NO_SHOW_GRACE,
    ) -> None:
        self.reservation_repo = reservation_repo
        self.slot_repo = slot_repo
        self.uow = uow
        self.no_show_grace = (
            no_show_grace  # 시작 후 이만큼 지나야 노쇼 (공장이 환경변수로 넣어 줌)
        )

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
        user: AuthenticatedUser | None,
        reservation_id: int,
        now: datetime,
        by: CancelledBy = CancelledBy.CUSTOMER,
        reason: CancelReason = CancelReason.CUSTOMER_REQUEST,
        note: str | None = None,
    ) -> tuple[Reservation, TimeSlot]:
        """예약을 취소한다. 대상 확인 -> 슬롯 잠금 -> 예약 잠금 -> 취소 -> (시작 전이면) 자리 반납 -> 저장 -> commit (한 묶음).
        기본값은 손님 취소. 운영자·관리자는 창구가 by·reason을 넣어 부르고, 자동 노쇼는 user 없이 SYSTEM으로 부른다."""
        # 1. 잠그기 전에 먼저 꺼내서 어느 슬롯인지 알아내고, 이 사람이 다룰 수 있는 예약인지 본다. 아니면 404
        found = await self.reservation_repo.get(reservation_id)
        if found is None:
            raise NotFoundError()
        await self._check_target(found, user, by)

        # 2. 생성과 같은 순서로 잠근다: 슬롯 -> 예약 (순서가 같아야 데드락이 안 생긴다.)
        slot, reservation = await self._lock(found)

        # 3. 잠근 뒤 읽은 최신 상태로 취소한다. 이유·시각·입장 여부가 안 맞으면 도메인이 409/422 에러를 낸다.
        reservation.cancel(
            slot_starts_at=slot.starts_at,
            now=now,
            by=by,
            reason=reason,
            grace=self.no_show_grace,
            note=note,
        )

        # 4. 시작 전에 취소했을 때만 자리를 돌려준다 (노쇼·시작 후 관리자 취소는 이미 지난 자리)
        if reservation.returns_seat(slot.starts_at):
            slot.release(reservation.party_size)
            await self.slot_repo.save(slot)
        await self.reservation_repo.save(reservation)

        # 5. 맨 끝에 한 번만 확정한다. 두 잠금도 여기서 풀린다.
        await self.uow.commit()
        return reservation, slot

    async def check_in(
        self, user: AuthenticatedUser, reservation_id: int, now: datetime
    ) -> tuple[Reservation, TimeSlot]:
        """손님이 왔다고 기록한다 (그 식당 운영자만). 대상 확인 -> 슬롯 잠금 -> 예약 잠금 -> 입장 기록 -> 저장 -> commit."""
        found = await self.reservation_repo.get(reservation_id)
        if found is None:
            raise NotFoundError()
        await self._check_target(found, user, CancelledBy.OWNER)

        slot, reservation = await self._lock(found)
        reservation.check_in(
            now=now, slot_starts_at=slot.starts_at, slot_ends_at=slot.ends_at
        )
        await self.reservation_repo.save(reservation)
        await self.uow.commit()
        return reservation, slot

    async def expire_no_shows(self, now: datetime) -> int:
        """자동 노쇼: 확정 + 입장 안 함 + 시작 후 유예 시간이 지난 예약을 SYSTEM·NO_SHOW로 하나씩 취소한다.
        찾은 뒤 그 사이에 취소·입장·삭제된 예약은 건너뛴다. 처리한 개수를 돌려준다."""
        handled = 0
        for reservation_id in await self.reservation_repo.list_no_show_ids(
            now, self.no_show_grace
        ):
            try:
                await self.cancel(
                    None,
                    reservation_id,
                    now,
                    by=CancelledBy.SYSTEM,
                    reason=CancelReason.NO_SHOW,
                )
            except (
                AlreadyCancelledError,
                AlreadyCheckedInError,
                NoShowTooEarlyError,
                NotFoundError,
            ):
                continue  # 다른 요청이 먼저 처리한 예약. 오류가 아니라 건너뜀
            handled += 1
        return handled

    async def _check_target(
        self, found: Reservation, user: AuthenticatedUser | None, by: CancelledBy
    ) -> None:
        """누가(by) 이 예약을 다룰 수 있는지 잠그기 전에 본다. 아니면 404 (남의 예약은 있는지조차 숨김)."""
        if by is CancelledBy.SYSTEM:
            return  # 자동 노쇼는 사람이 아니라서 대상 확인 없음
        if user is None:
            raise NotFoundError()
        if by is CancelledBy.CUSTOMER:
            allowed = found.user_id == user.user_id
        elif by is CancelledBy.OWNER:
            # 예약 -> 슬롯 -> 식당(삭제 안 된 것)의 주인이 나여야 한다
            owner_id = await self.reservation_repo.restaurant_owner_of(found.id)
            allowed = (
                user.is_owner() and owner_id is not None and owner_id == user.user_id
            )
        else:  # 관리자는 모든 예약 (식당이 삭제돼도)
            allowed = user.is_admin()
        if not allowed:
            raise NotFoundError()

    async def _lock(self, found: Reservation) -> tuple[TimeSlot, Reservation]:
        """생성과 같은 순서로 잠근다: 슬롯 -> 예약. 잠근 뒤 읽은 최신 값을 돌려준다."""
        slot = await self.slot_repo.get_for_update(found.slot_id)
        if slot is None:
            raise NotFoundError()
        reservation = await self.reservation_repo.get_for_update(found.id)
        if reservation is None:
            raise NotFoundError()
        return slot, reservation
