# [담당 4] 예약 서비스 테스트 : 가짜 저장소로 예약 생성.취소.노쇼.입장 확인 흐름, 잠그기 전에 시간 제한 걸기 확인
import uuid
from datetime import datetime, timedelta

import pytest

from common.errors import NotFoundError
from common.schemas import SEOUL
from common.unit_of_work import ConflictError, UnitOfWork
from reservation.application.service import ReservationService
from reservation.domain.exceptions import (
    AlreadyCancelledError,
    AlreadyCheckedInError,
    CancellationNotAllowedError,
    CancelNoteRequiredError,
    DuplicateReservationError,
    NoShowTooEarlyError,
)
from reservation.domain.repository import ReservationRepository
from reservation.domain.reservation import (
    CancelledBy,
    CancelReason,
    Reservation,
    ReservationStatus,
)
from reservation.domain.value_object import Actor, ActorRole
from slot.domain.exceptions import SlotSoldOut
from slot.domain.repository import SlotRepository
from slot.domain.time_slot import TimeSlot


class InMemoryReservationRepository(ReservationRepository):
    """DB 대신 리스트에 예약을 보관하는 가짜 저장소"""

    def __init__(self, lock_log: list[str]) -> None:
        self.reservations: list[Reservation] = []
        self.lock_log = lock_log  # 잠근 순서를 적는 기록장 (슬롯 저장소와 같이 씀)
        self.conflict = False  # True면 DB 규칙(확정 예약은 사람, 슬롯당 하나)이 막은 상황을 흉내 낸다.
        self.restaurant_owner_id: uuid.UUID | None = (
            None  # 예약이 속한 식당의 주인 (None이면 식당 없음·삭제)
        )
        self.slot_starts_at: datetime | None = None  # 노쇼 대상 찾기용 슬롯 시작 시각

    async def set_time_limits(self) -> None:
        self.lock_log.append("time_limits")  # 진짜 DB 설정은 없고, 언제 불렸는지만 기록

    async def exists_confirmed(self, user_id: uuid.UUID, slot_id: int) -> bool:
        return any(
            r.user_id == user_id
            and r.slot_id == slot_id
            and r.status is ReservationStatus.CONFIRMED
            for r in self.reservations
        )

    async def add(self, reservation: Reservation) -> Reservation:
        if self.conflict:
            raise ConflictError()  # 진짜 어댑터가 flush에서 난 IntegrityError를 번역해 던지는 것과 같은 에러
        reservation.id = len(self.reservations) + 1  # DB가 번호를 붙여주는 흉내
        self.reservations.append(reservation)
        return reservation

    async def get(self, reservation_id: int) -> Reservation | None:
        return next((r for r in self.reservations if r.id == reservation_id), None)

    async def get_for_update(self, reservation_id: int) -> Reservation | None:
        self.lock_log.append("reservation")  # 진짜로 잠그진 않고, 잠근 순서만 기록

        return await self.get(reservation_id)  # 메모리에는 잠글 게 없어서 그냥 꺼냄

    async def save(self, reservation: Reservation) -> None:
        pass  # 같은 객체를 들고 있어서 따로 반영할 게 없음

    async def restaurant_owner_of(self, reservation_id: int) -> uuid.UUID | None:
        if await self.get(reservation_id) is None:
            return None
        return self.restaurant_owner_id

    async def list_no_show_ids(self, now: datetime, grace: timedelta) -> list[int]:
        return [
            r.id
            for r in self.reservations
            if r.status is ReservationStatus.CONFIRMED
            and r.checked_in_at is None
            and self.slot_starts_at is not None
            and self.slot_starts_at <= now - grace
        ]


class InMemorySlotRepository(SlotRepository):
    """DB 대신 리스트에 슬롯을 보관하는 가짜 저장소"""

    def __init__(self, slots: list[TimeSlot], lock_log: list[str]) -> None:
        self.slots = slots
        self.lock_log = lock_log  # 잠근 순서를 적는 기록장 (예약 저장소와 같이 씀)

    async def get_for_update(self, slot_id: int) -> TimeSlot | None:
        self.lock_log.append("slot")  # 진짜로 잠그진 않고, 잠근 순서만 기록
        return next(
            (s for s in self.slots if s.id == slot_id), None
        )  # 메모리에는 잠글 게 없어서 그냥 꺼냄

    async def save(self, slot: TimeSlot) -> None:
        pass  # 같은 객체를 들고 있어서 따로 반영할 게 없음

    async def list_for_day(
        self, restaurant_id: int, start: datetime, end: datetime
    ) -> list[TimeSlot]:
        raise NotImplementedError  # 예약 서비스는 안 씀

    async def restaurant_exists(self, restaurant_id: int) -> bool:
        raise NotImplementedError  # 예약 서비스는 안 씀


class FakeUnitOfWork(UnitOfWork):
    """commit·release가 몇 번 불렸는지 세는 가짜 도장 담당"""

    def __init__(self) -> None:
        self.commits = 0
        self.releases = 0  # 확정 없이 트랜잭션을 끝내 잠금을 놓은 횟수

    async def commit(self) -> None:
        self.commits += 1

    async def release(self) -> None:
        self.releases += 1


USER_ID = uuid.UUID("00000000-0000-4000-8000-000000000001")
OTHER_USER_ID = uuid.UUID("00000000-0000-4000-8000-000000000002")
OWNER_ID = uuid.UUID("00000000-0000-4000-8000-000000000003")
OTHER_OWNER_ID = uuid.UUID("00000000-0000-4000-8000-000000000004")
ADMIN_ID = uuid.UUID("00000000-0000-4000-8000-000000000005")

CUSTOMER = Actor(user_id=USER_ID, role=ActorRole.CUSTOMER)  # 예약한 손님
OTHER_CUSTOMER = Actor(user_id=OTHER_USER_ID, role=ActorRole.CUSTOMER)
OWNER = Actor(user_id=OWNER_ID, role=ActorRole.OWNER)  # 1번 식당 주인
OTHER_OWNER = Actor(user_id=OTHER_OWNER_ID, role=ActorRole.OWNER)
ADMIN = Actor(user_id=ADMIN_ID, role=ActorRole.ADMIN)

NOW = datetime(2026, 12, 3, 17, 0, tzinfo=SEOUL)
STARTS_AT = datetime(2026, 12, 3, 18, 0, tzinfo=SEOUL)
ENDS_AT = datetime(2026, 12, 3, 19, 0, tzinfo=SEOUL)
GRACE = timedelta(minutes=15)  # 노쇼 유예 시간
NO_SHOW_TIME = STARTS_AT + GRACE  # 이때부터 노쇼로 볼 수 있다


@pytest.fixture
def slot() -> TimeSlot:
    # 7번 슬롯 : 정원 10명, 지금 2명 예약됨, 한 팀 최대 4명
    return TimeSlot(
        id=7,
        restaurant_id=1,
        starts_at=STARTS_AT,
        ends_at=ENDS_AT,
        capacity=10,
        reserved_guests=2,
        max_party_size=4,
    )


@pytest.fixture
def lock_log() -> list[str]:
    return []  # 두 가짜 저장소가 같이 쓰는 잠금 기록장


@pytest.fixture
def reservation_repo(lock_log) -> InMemoryReservationRepository:
    repo = InMemoryReservationRepository(lock_log)
    repo.restaurant_owner_id = OWNER_ID  # 7번 슬롯은 OWNER의 1번 식당 것
    repo.slot_starts_at = STARTS_AT
    return repo


@pytest.fixture
def uow() -> FakeUnitOfWork:
    return FakeUnitOfWork()


@pytest.fixture
def service(reservation_repo, slot, uow, lock_log) -> ReservationService:
    return ReservationService(
        reservation_repo=reservation_repo,
        slot_repo=InMemorySlotRepository([slot], lock_log),
        uow=uow,
        no_show_grace=GRACE,
    )


async def test_create_saves_reservation_and_reserves_seats(
    service, reservation_repo, slot, uow
):
    reservation, returned_slot = await service.create(
        user_id=USER_ID, slot_id=7, party_size=2, contact_phone=None, now=NOW
    )

    # 예약이 저장되고 번호가 붙는다.
    assert reservation.id == 1
    assert reservation_repo.reservations == [reservation]
    # 슬롯 자리가 2명 늘어난다 (2명 -> 4명).
    assert returned_slot is slot
    assert slot.reserved_guests == 4
    # 맨 끝에 한 번만 확정한다.
    assert uow.commits == 1


async def test_create_unknown_slot_raises_not_found(service, reservation_repo, uow):
    # 없는 슬롯 번호로 예약하면 404가 나고, 아무것도 저장, 확정하지 않는다.
    with pytest.raises(NotFoundError):
        await service.create(
            user_id=USER_ID, slot_id=999, party_size=2, contact_phone=None, now=NOW
        )

    assert reservation_repo.reservations == []
    assert uow.commits == 0


async def test_create_twice_raises_duplicate(service, reservation_repo, slot, uow):
    # 같은 사람이 같은 슬롯을 두 번 예약하면, 두 번째는 409가 나고 자리도 다시 늘지 않는다.
    await service.create(
        user_id=USER_ID, slot_id=7, party_size=2, contact_phone=None, now=NOW
    )

    with pytest.raises(DuplicateReservationError):
        await service.create(
            user_id=USER_ID, slot_id=7, party_size=2, contact_phone=None, now=NOW
        )

    assert len(reservation_repo.reservations) == 1
    assert slot.reserved_guests == 4
    assert uow.commits == 1


async def test_create_sold_out_raises_and_keeps_seats(
    service, reservation_repo, slot, uow
):
    # 남은 자리(1명)보다 많이 예약하면 409가 나고, 자리 수는 그대로다.
    slot.reserved_guests = 9

    with pytest.raises(SlotSoldOut):
        await service.create(
            user_id=USER_ID, slot_id=7, party_size=2, contact_phone=None, now=NOW
        )

    assert reservation_repo.reservations == []
    assert slot.reserved_guests == 9
    assert uow.commits == 0


async def test_cancel_releases_seats_and_commits(service, slot, uow):
    # 내 예약을 취소하면 취소 상태가 되고, 자리가 반납되고, 한 번 더 확정한다.
    created, _ = await service.create(
        user_id=USER_ID, slot_id=7, party_size=2, contact_phone=None, now=NOW
    )

    cancelled, returned_slot = await service.cancel(
        user=CUSTOMER, reservation_id=created.id, now=NOW
    )

    assert cancelled.status is ReservationStatus.CANCELLED
    assert cancelled.cancelled_at == NOW
    assert returned_slot is slot
    assert slot.reserved_guests == 2
    assert uow.commits == 2


async def test_cancel_unknown_reservation_raises_not_found(service, uow):
    # 없는 예약 번호를 취소하면 404가 나고 확정하지 않는다.
    with pytest.raises(NotFoundError):
        await service.cancel(user=CUSTOMER, reservation_id=999, now=NOW)

    assert uow.commits == 0


async def test_cancel_other_users_reservation_raises_not_found(service, slot, uow):
    # 남의 예약을 취소하려 하면 있는지조차 숨기려고 404가 나고, 예약과 자리는 그대로다.
    created, _ = await service.create(
        user_id=USER_ID, slot_id=7, party_size=2, contact_phone=None, now=NOW
    )

    with pytest.raises(NotFoundError):
        await service.cancel(user=OTHER_CUSTOMER, reservation_id=created.id, now=NOW)

    assert created.status is ReservationStatus.CONFIRMED
    assert slot.reserved_guests == 4
    assert uow.commits == 1


async def test_cancel_twice_raises_already_cancelled(service, slot, uow):
    # 두 번 취소하면 두 번째는 409가 나고, 자리를 또 반납하지 않는다.
    created, _ = await service.create(
        user_id=USER_ID, slot_id=7, party_size=2, contact_phone=None, now=NOW
    )
    await service.cancel(user=CUSTOMER, reservation_id=created.id, now=NOW)

    with pytest.raises(AlreadyCancelledError):
        await service.cancel(user=CUSTOMER, reservation_id=created.id, now=NOW)

    assert slot.reserved_guests == 2
    assert uow.commits == 2


async def test_cancel_after_slot_started_raises_not_allowed(service, slot, uow):
    # 슬롯이 시작된 뒤에 취소하면 409가 나고, 예약과 자리는 그대로다.
    created, _ = await service.create(
        user_id=USER_ID, slot_id=7, party_size=2, contact_phone=None, now=NOW
    )

    with pytest.raises(CancellationNotAllowedError):
        await service.cancel(user=CUSTOMER, reservation_id=created.id, now=STARTS_AT)

    assert created.status is ReservationStatus.CONFIRMED
    assert slot.reserved_guests == 4
    assert uow.commits == 1


async def test_create_locks_slot(service, lock_log):
    # 예약을 만들 때는 슬롯만 잠근다. (예약은 아직 없으니까)
    await service.create(
        user_id=USER_ID, slot_id=7, party_size=2, contact_phone=None, now=NOW
    )

    # 잠그기 전에 시간 제한부터 건다 (기다림·멈춤에 상한이 있어야 잠금이 영원히 안 남는다)
    assert lock_log == ["time_limits", "slot"]


async def test_cancel_locks_slot_before_reservation(service, lock_log):
    # 취소할 때는 생성과 같은 순서(슬롯 -> 예약)로 잡는다. 순서가 다르면 데드락이 생길 수 있다.
    created, _ = await service.create(
        user_id=USER_ID, slot_id=7, party_size=2, contact_phone=None, now=NOW
    )
    lock_log.clear()  # 생성 때 적힌 기록은 지우고, 취소 때 기록만 본다

    await service.cancel(user=CUSTOMER, reservation_id=created.id, now=NOW)

    # 시간 제한 -> 슬롯 -> 예약 순서 (시간 제한은 잠금 없이 먼저 읽는 단계보다도 앞)
    assert lock_log == ["time_limits", "slot", "reservation"]


async def test_create_db_conflict_raises_duplicate(service, reservation_repo, uow):
    # 서비스가 중복 확인을 지나쳤어도, 저장(add)할 때 DB 규칙이 막으면(ConflictError) 409 중복 예약 에러로 바꿔 준다.
    reservation_repo.conflict = True

    with pytest.raises(DuplicateReservationError):
        await service.create(
            user_id=USER_ID, slot_id=7, party_size=2, contact_phone=None, now=NOW
        )

    assert reservation_repo.reservations == []
    assert uow.commits == 0


async def test_owner_cancels_reservation_of_own_restaurant(service, slot, uow):
    # 1번 식당 주인은 그 식당 손님 예약을 전화 요청으로 취소할 수 있고, 시작 전이라 자리도 반납된다.
    created, _ = await service.create(
        user_id=USER_ID, slot_id=7, party_size=2, contact_phone=None, now=NOW
    )

    cancelled, _ = await service.cancel(
        user=OWNER,
        reservation_id=created.id,
        now=NOW,
        by=CancelledBy.OWNER,
        reason=CancelReason.PHONE_REQUEST,
    )

    assert cancelled.status is ReservationStatus.CANCELLED
    assert cancelled.cancelled_by is CancelledBy.OWNER
    assert cancelled.cancel_reason is CancelReason.PHONE_REQUEST
    assert slot.reserved_guests == 2
    assert uow.commits == 2


async def test_other_owner_cancel_raises_not_found(service, slot, uow):
    # 다른 식당 주인이 취소하려 하면 예약이 있는지조차 숨기려고 404가 나고, 예약과 자리는 그대로다.
    created, _ = await service.create(
        user_id=USER_ID, slot_id=7, party_size=2, contact_phone=None, now=NOW
    )

    with pytest.raises(NotFoundError):
        await service.cancel(
            user=OTHER_OWNER,
            reservation_id=created.id,
            now=NOW,
            by=CancelledBy.OWNER,
            reason=CancelReason.PHONE_REQUEST,
        )

    assert created.status is ReservationStatus.CONFIRMED
    assert slot.reserved_guests == 4
    assert uow.commits == 1


async def test_owner_cannot_cancel_through_customer_path(service, slot, uow):
    # 손님 취소(기본값)로 부르면 운영자도 내 예약만 된다. 손님 예약은 운영자 주소로 해야 한다
    created, _ = await service.create(
        user_id=USER_ID, slot_id=7, party_size=2, contact_phone=None, now=NOW
    )

    with pytest.raises(NotFoundError):
        await service.cancel(user=OWNER, reservation_id=created.id, now=NOW)

    assert created.status is ReservationStatus.CONFIRMED


async def test_owner_cancel_when_restaurant_is_gone_raises_not_found(
    service, reservation_repo, uow
):
    # 식당이 삭제돼 주인을 못 찾으면 운영자는 404다.
    created, _ = await service.create(
        user_id=USER_ID, slot_id=7, party_size=2, contact_phone=None, now=NOW
    )
    reservation_repo.restaurant_owner_id = None

    with pytest.raises(NotFoundError):
        await service.cancel(
            user=OWNER,
            reservation_id=created.id,
            now=NOW,
            by=CancelledBy.OWNER,
            reason=CancelReason.PHONE_REQUEST,
        )

    assert uow.commits == 1


async def test_admin_cancels_any_reservation_with_note(service, slot, uow):
    # 관리자는 어느 식당 예약이든 메모를 남기고 취소할 수 있다.
    created, _ = await service.create(
        user_id=USER_ID, slot_id=7, party_size=2, contact_phone=None, now=NOW
    )

    cancelled, _ = await service.cancel(
        user=ADMIN,
        reservation_id=created.id,
        now=NOW,
        by=CancelledBy.ADMIN,
        reason=CancelReason.SYSTEM_ERROR,
        note="중복 결제 정리",
    )

    assert cancelled.cancelled_by is CancelledBy.ADMIN
    assert cancelled.cancel_note == "중복 결제 정리"
    assert slot.reserved_guests == 2
    assert uow.commits == 2


async def test_admin_cancel_without_note_is_rejected(service, slot, uow):
    # 관리자가 메모 없이 취소하면 422이고, 예약과 자리는 그대로다.
    created, _ = await service.create(
        user_id=USER_ID, slot_id=7, party_size=2, contact_phone=None, now=NOW
    )

    with pytest.raises(CancelNoteRequiredError):
        await service.cancel(
            user=ADMIN,
            reservation_id=created.id,
            now=NOW,
            by=CancelledBy.ADMIN,
            reason=CancelReason.OTHER,
        )

    assert created.status is ReservationStatus.CONFIRMED
    assert slot.reserved_guests == 4
    assert uow.commits == 1


async def test_admin_cancel_after_start_keeps_seats(service, slot, uow):
    # 관리자는 시작 후에도 취소할 수 있지만, 이미 지난 자리라 좌석은 돌려주지 않는다.
    created, _ = await service.create(
        user_id=USER_ID, slot_id=7, party_size=2, contact_phone=None, now=NOW
    )

    cancelled, _ = await service.cancel(
        user=ADMIN,
        reservation_id=created.id,
        now=STARTS_AT,
        by=CancelledBy.ADMIN,
        reason=CancelReason.OTHER,
        note="손님 요청",
    )

    assert cancelled.status is ReservationStatus.CANCELLED
    assert slot.reserved_guests == 4
    assert uow.commits == 2


async def test_admin_cancels_even_if_restaurant_is_gone(service, reservation_repo):
    # 식당이 삭제돼도 관리자는 식당을 보지 않고 취소할 수 있다.
    created, _ = await service.create(
        user_id=USER_ID, slot_id=7, party_size=2, contact_phone=None, now=NOW
    )
    reservation_repo.restaurant_owner_id = None

    cancelled, _ = await service.cancel(
        user=ADMIN,
        reservation_id=created.id,
        now=NOW,
        by=CancelledBy.ADMIN,
        reason=CancelReason.OTHER,
        note="식당 폐업",
    )

    assert cancelled.status is ReservationStatus.CANCELLED


async def test_owner_marks_no_show_and_keeps_seats(service, slot, uow):
    # 시작 15분 뒤 운영자가 노쇼로 처리하면 취소(이유 NO_SHOW)되고, 좌석은 돌려주지 않는다.
    created, _ = await service.create(
        user_id=USER_ID, slot_id=7, party_size=2, contact_phone=None, now=NOW
    )

    cancelled, _ = await service.cancel(
        user=OWNER,
        reservation_id=created.id,
        now=NO_SHOW_TIME,
        by=CancelledBy.OWNER,
        reason=CancelReason.NO_SHOW,
    )

    assert cancelled.cancel_reason is CancelReason.NO_SHOW
    assert slot.reserved_guests == 4
    assert uow.commits == 2


async def test_owner_no_show_too_early_is_rejected(service, uow):
    # 유예 시간 전에는 노쇼로 처리할 수 없다.
    created, _ = await service.create(
        user_id=USER_ID, slot_id=7, party_size=2, contact_phone=None, now=NOW
    )

    with pytest.raises(NoShowTooEarlyError):
        await service.cancel(
            user=OWNER,
            reservation_id=created.id,
            now=NO_SHOW_TIME - timedelta(seconds=1),
            by=CancelledBy.OWNER,
            reason=CancelReason.NO_SHOW,
        )

    assert uow.commits == 1


async def test_owner_checks_in_then_no_show_is_rejected(service, uow):
    # 운영자가 입장 확인한 예약은 노쇼로 처리할 수 없다.
    created, _ = await service.create(
        user_id=USER_ID, slot_id=7, party_size=2, contact_phone=None, now=NOW
    )

    checked, _ = await service.check_in(
        user=OWNER, reservation_id=created.id, now=STARTS_AT
    )
    assert checked.checked_in_at == STARTS_AT

    with pytest.raises(AlreadyCheckedInError):
        await service.cancel(
            user=OWNER,
            reservation_id=created.id,
            now=NO_SHOW_TIME,
            by=CancelledBy.OWNER,
            reason=CancelReason.NO_SHOW,
        )

    assert uow.commits == 2  # 예약 1번 + 입장 확인 1번


async def test_other_owner_cannot_check_in(service, uow):
    # 다른 식당 주인은 입장 확인을 할 수 없다 (404).
    created, _ = await service.create(
        user_id=USER_ID, slot_id=7, party_size=2, contact_phone=None, now=NOW
    )

    with pytest.raises(NotFoundError):
        await service.check_in(
            user=OTHER_OWNER, reservation_id=created.id, now=STARTS_AT
        )

    assert created.checked_in_at is None
    assert uow.commits == 1


async def test_owner_cancel_locks_slot_before_reservation(service, lock_log):
    # 운영자가 취소할 때도 잠금 순서는 슬롯 -> 예약으로 같다.
    created, _ = await service.create(
        user_id=USER_ID, slot_id=7, party_size=2, contact_phone=None, now=NOW
    )
    lock_log.clear()

    await service.cancel(
        user=OWNER,
        reservation_id=created.id,
        now=NOW,
        by=CancelledBy.OWNER,
        reason=CancelReason.PHONE_REQUEST,
    )

    # 시간 제한 -> 슬롯 -> 예약 순서 (시간 제한은 잠금 없이 먼저 읽는 단계보다도 앞)
    assert lock_log == ["time_limits", "slot", "reservation"]


async def test_expire_no_shows_handles_only_due_and_not_checked_in(service, slot):
    # 자동 노쇼: 시작 15분 지남 + 입장 안 함 예약만 처리하고, 입장한 예약은 건너뛴다.
    no_show, _ = await service.create(
        user_id=USER_ID, slot_id=7, party_size=2, contact_phone=None, now=NOW
    )
    came, _ = await service.create(
        user_id=OTHER_USER_ID, slot_id=7, party_size=2, contact_phone=None, now=NOW
    )
    await service.check_in(user=OWNER, reservation_id=came.id, now=STARTS_AT)

    # 아직 15분 전이면 아무것도 안 한다
    assert await service.expire_no_shows(NO_SHOW_TIME - timedelta(seconds=1)) == 0

    handled = await service.expire_no_shows(NO_SHOW_TIME)

    assert handled == 1
    assert no_show.cancelled_by is CancelledBy.SYSTEM
    assert no_show.cancel_reason is CancelReason.NO_SHOW
    assert came.status is ReservationStatus.CONFIRMED  # 입장한 손님은 그대로
    assert slot.reserved_guests == 6  # 노쇼여도 좌석은 안 돌려줌 (2 + 2 + 2)
    # 두 번 돌려도 이미 처리된 건 다시 처리하지 않는다
    assert await service.expire_no_shows(NO_SHOW_TIME) == 0


async def test_check_in_sets_time_limits_before_locking(service, lock_log):
    # 입장 확인도 잠그기 전에 시간 제한부터 건다.
    created, _ = await service.create(
        user_id=USER_ID, slot_id=7, party_size=2, contact_phone=None, now=NOW
    )
    lock_log.clear()

    await service.check_in(user=OWNER, reservation_id=created.id, now=STARTS_AT)

    assert lock_log == ["time_limits", "slot", "reservation"]


async def test_cancel_of_missing_reservation_still_sets_time_limits_first(
    service, lock_log
):
    # 없는 예약이라 404로 끝나도, 시간 제한은 맨 처음에 걸려 있다 (첫 조회도 상한 안에서 돈다).
    with pytest.raises(NotFoundError):
        await service.cancel(user=CUSTOMER, reservation_id=999, now=NOW)

    assert lock_log == ["time_limits"]


async def test_expire_no_shows_releases_lock_when_skipping(
    service, reservation_repo, uow, monkeypatch
):
    # 자동 노쇼가 건너뛴 예약(그 사이 이미 취소됨)의 잠금은 바로 놓고, 다음 예약은 그대로 처리한다.
    already, _ = await service.create(
        user_id=USER_ID, slot_id=7, party_size=2, contact_phone=None, now=NOW
    )
    due, _ = await service.create(
        user_id=OTHER_USER_ID, slot_id=7, party_size=2, contact_phone=None, now=NOW
    )
    await service.cancel(user=CUSTOMER, reservation_id=already.id, now=NOW)
    commits_before = uow.commits

    async def stale_ids(now, grace):
        return [
            already.id,
            due.id,
        ]  # 찾을 때는 확정이었는데 처리하려니 이미 취소된 상황

    monkeypatch.setattr(reservation_repo, "list_no_show_ids", stale_ids)

    handled = await service.expire_no_shows(NO_SHOW_TIME)

    assert handled == 1
    assert uow.releases == 1  # 건너뛴 1건은 확정 없이 끝내서 잠금을 놓았다
    assert uow.commits == commits_before + 1  # 처리한 1건만 확정
    assert due.cancel_reason is CancelReason.NO_SHOW
