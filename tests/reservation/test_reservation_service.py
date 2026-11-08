# [담당 4] 예약 서비스 테스트 : 가짜 저장소로 예약 생성.취소 흐름 확인
import uuid
import pytest
from datetime import datetime

from common.schemas import SEOUL
from common.unit_of_work import UnitOfWork
from common.errors import NotFoundError
from reservation.domain.exceptions import DuplicateReservationError
from reservation.application.service import ReservationService
from reservation.domain.repository import ReservationRepository
from reservation.domain.reservation import Reservation, ReservationStatus
from slot.domain.repository import SlotRepository
from slot.domain.time_slot import TimeSlot
from slot.domain.exceptions import SlotSoldOut

class InMemoryReservationRepository(ReservationRepository):
    """DB 대신 리스트에 예약을 보관하는 가짜 저장소"""

    def __init__(self) -> None:
        self.reservations: list[Reservation] = []

    async def exists_confirmed(self, user_id: uuid.UUID, slot_id: int) -> bool:
        return any(
            r.user_id == user_id
            and r.slot_id == slot_id
            and r.status is ReservationStatus.CONFIRMED
            for r in self.reservations
        )

    async def add(self, reservation: Reservation) -> Reservation:
        reservation.id = len(self.reservations) + 1 # DB가 번호를 붙여주는 흉내
        self.reservations.append(reservation)
        return reservation

    async def get(self, reservation_id: int) -> Reservation | None:
        return next((r for r in self.reservations if r.id == reservation_id), None)

    async def get_for_update(self, reservation_id: int) -> Reservation | None:
        return await self.get(reservation_id) # 메모리에는 잠글 게 없어서 그냥 꺼냄

    async def save(self, reservation: Reservation) -> None:
        pass # 같은 객체를 들고 있어서 따로 반영할 게 없음


class InMemorySlotRepository(SlotRepository):
    """DB 대신 리스트에 슬롯을 보관하는 가짜 저장소"""

    def __init__(self, slots: list[TimeSlot]) -> None:
        self.slots = slots

    async def get_for_update(self, slot_id: int) -> TimeSlot | None:
        return next((s for s in self.slots if s.id == slot_id), None) # 메모리에는 잠글 게 없어서 그냥 꺼냄

    async def save(self, slot: TimeSlot) -> None:
        pass # 같은 객체를 들고 있어서 따로 반영할 게 없음

    async def list_for_day(self, restaurant_id: int, start: datetime, end: datetime) -> list[TimeSlot]:
        raise NotImplementedError # 예약 서비스는 안 씀

    async def restaurant_exists(self, restaurant_id: int) -> bool:
        raise NotImplementedError # 예약 서비스는 안 씀


class FakeUnitOfWork(UnitOfWork):
    """commit이 몇 번 불렸는지 세는 가짜 도장 담당"""

    def __init__(self) -> None:
        self.commits = 0

    async def commit(self) -> None:
        self.commits += 1

USER_ID = uuid.UUID("00000000-0000-4000-8000-000000000001")
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
def reservation_repo() -> InMemoryReservationRepository:
    return InMemoryReservationRepository()

@pytest.fixture
def uow() -> FakeUnitOfWork:
    return FakeUnitOfWork()

@pytest.fixture
def service(reservation_repo, slot, uow) -> ReservationService:
    return ReservationService(
        reservation_repo=reservation_repo,
        slot_repo=InMemorySlotRepository([slot]),
        uow=uow,
    )

async def test_create_saves_reservation_and_reserves_seats(service, reservation_repo, slot, uow):
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

async def test_create_sold_out_raises_and_keeps_seats(service, reservation_repo, slot, uow):
    # 남은 자리(1명)보다 많이 예약하면 409가 나고, 자리 수는 그대로다.
    slot.reserved_guests = 9

    with pytest.raises(SlotSoldOut):
        await service.create(
            user_id=USER_ID, slot_id=7, party_size=2, contact_phone=None, now=NOW
        )

    assert reservation_repo.reservations == []
    assert slot.reserved_guests == 9
    assert uow.commits == 0