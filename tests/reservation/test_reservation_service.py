# [담당 4] 예약 서비스 테스트 : 가짜 저장소로 예약 생성.취소 흐름 확인
import uuid
from datetime import datetime

import pytest

from auth.domain.value_object import AuthenticatedUser, AuthRole
from common.errors import NotFoundError
from common.schemas import SEOUL
from common.unit_of_work import ConflictError, UnitOfWork
from reservation.application.service import ReservationService
from reservation.domain.exceptions import (
    AlreadyCancelledError,
    CancellationNotAllowedError,
    DuplicateReservationError,
)
from reservation.domain.repository import ReservationRepository
from reservation.domain.reservation import Reservation, ReservationStatus
from restaurant.domain.exceptions import RestaurantNotFoundError
from restaurant.domain.restaurant import Restaurant
from slot.domain.exceptions import SlotSoldOut
from slot.domain.repository import SlotRepository
from slot.domain.time_slot import TimeSlot


class InMemoryReservationRepository(ReservationRepository):
    """DB 대신 리스트에 예약을 보관하는 가짜 저장소"""

    def __init__(self, lock_log: list[str]) -> None:
        self.reservations: list[Reservation] = []
        self.lock_log = lock_log  # 잠근 순서를 적는 기록장 (슬롯 저장소와 같이 씀)
        self.conflict = False  # True면 DB 규칙(확정 예약은 사람, 슬롯당 하나)이 막은 상황을 흉내 낸다.

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
    """commit이 몇 번 불렸는지 세는 가짜 도장 담당"""

    def __init__(self) -> None:
        self.commits = 0

    async def commit(self) -> None:
        self.commits += 1


class FakeRestaurantService:
    """식당 번호로 식당을 꺼내 주는 가짜 식당 매니저 (취소 권한 확인용)"""

    def __init__(self, restaurants: list[Restaurant]) -> None:
        self.restaurants = restaurants

    async def get_restaurant(self, restaurant_id: int) -> Restaurant:
        for restaurant in self.restaurants:
            if restaurant.id == restaurant_id:
                return restaurant
        raise RestaurantNotFoundError()  # 진짜 식당 매니저와 같은 404


USER_ID = uuid.UUID("00000000-0000-4000-8000-000000000001")
OTHER_USER_ID = uuid.UUID("00000000-0000-4000-8000-000000000002")
OWNER_ID = uuid.UUID("00000000-0000-4000-8000-000000000003")
OTHER_OWNER_ID = uuid.UUID("00000000-0000-4000-8000-000000000004")
ADMIN_ID = uuid.UUID("00000000-0000-4000-8000-000000000005")

CUSTOMER = AuthenticatedUser(user_id=USER_ID, role=AuthRole.CUSTOMER)  # 예약한 손님
OTHER_CUSTOMER = AuthenticatedUser(user_id=OTHER_USER_ID, role=AuthRole.CUSTOMER)
OWNER = AuthenticatedUser(user_id=OWNER_ID, role=AuthRole.OWNER)  # 1번 식당 주인
OTHER_OWNER = AuthenticatedUser(user_id=OTHER_OWNER_ID, role=AuthRole.OWNER)
ADMIN = AuthenticatedUser(user_id=ADMIN_ID, role=AuthRole.ADMIN)

# 1번 식당 (7번 슬롯이 이 식당 것)
RESTAURANT = Restaurant(
    id=1, owner_id=OWNER_ID, name="테스트 식당", address="서울 중구", cuisine="한식"
)
NOW = datetime(2026, 12, 3, 17, 0, tzinfo=SEOUL)
STARTS_AT = datetime(2026, 12, 3, 18, 0, tzinfo=SEOUL)
ENDS_AT = datetime(2026, 12, 3, 19, 0, tzinfo=SEOUL)


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
    return InMemoryReservationRepository(lock_log)


@pytest.fixture
def uow() -> FakeUnitOfWork:
    return FakeUnitOfWork()


@pytest.fixture
def service(reservation_repo, slot, uow, lock_log) -> ReservationService:
    return ReservationService(
        reservation_repo=reservation_repo,
        slot_repo=InMemorySlotRepository([slot], lock_log),
        restaurant_service=FakeRestaurantService([RESTAURANT]),
        uow=uow,
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

    assert lock_log == ["slot"]


async def test_cancel_locks_slot_before_reservation(service, lock_log):
    # 취소할 때는 생성과 같은 순서(슬롯 -> 예약)로 잡는다. 순서가 다르면 데드락이 생길 수 있다.
    created, _ = await service.create(
        user_id=USER_ID, slot_id=7, party_size=2, contact_phone=None, now=NOW
    )
    lock_log.clear()  # 생성 때 적힌 기록은 지우고, 취소 때 기록만 본다

    await service.cancel(user=CUSTOMER, reservation_id=created.id, now=NOW)

    assert lock_log == ["slot", "reservation"]


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
    # 1번 식당 주인은 그 식당 슬롯의 손님 예약을 취소할 수 있고, 자리도 반납된다.
    created, _ = await service.create(
        user_id=USER_ID, slot_id=7, party_size=2, contact_phone=None, now=NOW
    )

    cancelled, _ = await service.cancel(user=OWNER, reservation_id=created.id, now=NOW)

    assert cancelled.status is ReservationStatus.CANCELLED
    assert slot.reserved_guests == 2
    assert uow.commits == 2


async def test_other_owner_cancel_raises_not_found(service, slot, uow):
    # 다른 식당 주인이 취소하려 하면 예약이 있는지조차 숨기려고 404가 나고, 예약과 자리는 그대로다.
    created, _ = await service.create(
        user_id=USER_ID, slot_id=7, party_size=2, contact_phone=None, now=NOW
    )

    with pytest.raises(NotFoundError):
        await service.cancel(user=OTHER_OWNER, reservation_id=created.id, now=NOW)

    assert created.status is ReservationStatus.CONFIRMED
    assert slot.reserved_guests == 4
    assert uow.commits == 1


async def test_admin_cancels_any_reservation(service, slot, uow):
    # 관리자는 어느 식당 예약이든 취소할 수 있다.
    created, _ = await service.create(
        user_id=USER_ID, slot_id=7, party_size=2, contact_phone=None, now=NOW
    )

    cancelled, _ = await service.cancel(user=ADMIN, reservation_id=created.id, now=NOW)

    assert cancelled.status is ReservationStatus.CANCELLED
    assert slot.reserved_guests == 2
    assert uow.commits == 2


async def test_admin_cancel_after_slot_started_raises_not_allowed(service, slot, uow):
    # 관리자도 슬롯이 시작된 뒤에는 취소할 수 없다 (시각 규칙은 누구에게나 같다).
    created, _ = await service.create(
        user_id=USER_ID, slot_id=7, party_size=2, contact_phone=None, now=NOW
    )

    with pytest.raises(CancellationNotAllowedError):
        await service.cancel(user=ADMIN, reservation_id=created.id, now=STARTS_AT)

    assert created.status is ReservationStatus.CONFIRMED
    assert slot.reserved_guests == 4
    assert uow.commits == 1


async def test_owner_cancel_unknown_reservation_raises_not_found(service, uow):
    # 운영자·관리자도 없는 예약 번호면 404가 난다.
    with pytest.raises(NotFoundError):
        await service.cancel(user=OWNER, reservation_id=999, now=NOW)

    assert uow.commits == 0


async def test_owner_cancel_locks_slot_before_reservation(service, lock_log):
    # 운영자가 취소할 때도 잠금 순서는 슬롯 -> 예약으로 같다.
    created, _ = await service.create(
        user_id=USER_ID, slot_id=7, party_size=2, contact_phone=None, now=NOW
    )
    lock_log.clear()

    await service.cancel(user=OWNER, reservation_id=created.id, now=NOW)

    assert lock_log == ["slot", "reservation"]


async def test_admin_cancels_even_if_restaurant_is_gone(
    reservation_repo, slot, uow, lock_log
):
    # 식당이 삭제돼 조회되지 않아도, 관리자는 식당을 보지 않고 취소할 수 있다.
    service = ReservationService(
        reservation_repo=reservation_repo,
        slot_repo=InMemorySlotRepository([slot], lock_log),
        restaurant_service=FakeRestaurantService([]),  # 식당이 하나도 없음
        uow=uow,
    )
    created, _ = await service.create(
        user_id=USER_ID, slot_id=7, party_size=2, contact_phone=None, now=NOW
    )

    cancelled, _ = await service.cancel(user=ADMIN, reservation_id=created.id, now=NOW)

    assert cancelled.status is ReservationStatus.CANCELLED
    assert slot.reserved_guests == 2
