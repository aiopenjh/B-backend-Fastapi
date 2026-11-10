# [담당 4] 예약 실제 DB 테스트 : 진짜 PostgreSQL로 예약 생성, 꽉 찬 슬롯, 동시 예약, 취소, 트랜잭션 시간 제한 확인
import asyncio
import os
import time
import uuid
from datetime import datetime, timedelta

import pytest
from dotenv import load_dotenv
from sqlalchemy import func, select, text, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from common.errors import NotFoundError
from common.model import Base, init_models
from common.schemas import SEOUL
from common.unit_of_work import ConflictError
from container import expire_no_shows_once
from reservation.application.service import ReservationService
from reservation.domain.exceptions import (
    AlreadyCancelledError,
    AlreadyCheckedInError,
    DuplicateReservationError,
    ReservationBusyError,
    ReservationTimeoutError,
)
from reservation.domain.reservation import CancelledBy, CancelReason, Reservation
from reservation.domain.value_object import Actor, ActorRole
from reservation.infrastructure.models import ReservationModel
from reservation.infrastructure.repositories import SQLAlchemyReservationRepository
from reservation.infrastructure.time_limits import (
    DEFAULT_TIME_LIMITS,
    TimeLimits,
    register_time_limit_errors,
)
from restaurant.infrastructure.models import RestaurantModel
from slot.domain.exceptions import SlotSoldOut
from slot.infrastructure.models import ReservationSlotModel
from slot.infrastructure.repositories import SQLAlchemySlotRepository
from user.infrastructure.models import UserModel
from user.infrastructure.unit_of_work import SQLAlchemyUnitOfWork

load_dotenv()
TEST_POSTGRES_URL = os.getenv("TEST_POSTGRES_URL")

# TEST_POSTGRES_URL이 없는 팀원은 이 파일 테스트를 건너뛴다 (다른 테스트는 그대로 돈다)
pytestmark = pytest.mark.skipif(
    TEST_POSTGRES_URL is None,
    reason="TEST_POSTGRES_URL이 없으면 실제 DB 테스트는 건너뛴다",
)

NOW = datetime(2030, 1, 1, 12, 0, tzinfo=SEOUL)
STARTS_AT = datetime(2030, 1, 1, 18, 0, tzinfo=SEOUL)
ENDS_AT = datetime(2030, 1, 1, 19, 0, tzinfo=SEOUL)
GRACE = timedelta(minutes=15)  # 노쇼 유예 시간
# 시간 제한 테스트용 짧은 값 (진짜 값 3초·5초·10초를 기다리면 테스트가 느려서)
SHORT_LIMITS = TimeLimits(
    lock=timedelta(milliseconds=500),
    statement=timedelta(seconds=1),
    idle_in_transaction=timedelta(seconds=1),
)


@pytest.fixture
async def session_factory():
    """테스트마다 표를 비우고 새로 만든 뒤, 끝나면 연결을 정리한다"""
    engine = create_async_engine(TEST_POSTGRES_URL)
    register_time_limit_errors(engine)  # 앱처럼 시간 초과 DB 오류를 예약 에러로 바꾼다
    init_models()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


async def add_user(session_factory, role: str = "CUSTOMER") -> uuid.UUID:
    async with session_factory() as session:
        user = UserModel(
            email=f"{uuid.uuid4()}@example.com",
            name="테스트",
            password_hash="x",
            phone="010-0000-0000",
            role=role,
        )
        session.add(user)
        await session.commit()
        return user.id


async def add_slot(
    session_factory, capacity: int, reserved_guests: int = 0
) -> tuple[int, uuid.UUID]:
    """식당 주인 + 식당 + 슬롯을 만들고 (슬롯 번호, 식당 주인 id)를 돌려준다"""
    owner_id = await add_user(session_factory, role="OWNER")
    async with session_factory() as session:
        restaurant = RestaurantModel(
            owner_id=owner_id, name="테스트 식당", address="서울 중구", cuisine="한식"
        )
        session.add(restaurant)
        await session.flush()  # 식당 id를 받아 슬롯에 넣으려고
        slot = ReservationSlotModel(
            restaurant_id=restaurant.id,
            starts_at=STARTS_AT,
            ends_at=ENDS_AT,
            capacity=capacity,
            reserved_guests=reserved_guests,
            max_party_size=4,
        )
        session.add(slot)
        await session.commit()
        return slot.id, owner_id


def make_service(
    session, time_limits: TimeLimits = DEFAULT_TIME_LIMITS
) -> ReservationService:
    # 요청 하나 = 세션 하나. 앱의 create_reservation_service와 같은 조립 (시간 제한은 기본값 3초·5초·10초)
    return ReservationService(
        reservation_repo=SQLAlchemyReservationRepository(session, time_limits),
        slot_repo=SQLAlchemySlotRepository(session),
        uow=SQLAlchemyUnitOfWork(session),
        no_show_grace=GRACE,
    )


async def reserve(
    session_factory,
    user_id: uuid.UUID,
    slot_id: int,
    party_size: int,
    contact_phone: str | None = None,
    time_limits: TimeLimits = DEFAULT_TIME_LIMITS,
):
    async with session_factory() as session:
        return await make_service(session, time_limits).create(
            user_id=user_id,
            slot_id=slot_id,
            party_size=party_size,
            contact_phone=contact_phone,
            now=NOW,
        )


async def cancel(
    session_factory,
    user: Actor | None,
    reservation_id: int,
    now: datetime = NOW,
    by: CancelledBy = CancelledBy.CUSTOMER,
    reason: CancelReason = CancelReason.CUSTOMER_REQUEST,
    note: str | None = None,
):
    async with session_factory() as session:
        return await make_service(session).cancel(
            user=user,
            reservation_id=reservation_id,
            now=now,
            by=by,
            reason=reason,
            note=note,
        )


async def read_reservation(session_factory, reservation_id: int) -> ReservationModel:
    """새 연결로 예약 한 줄을 그대로 읽는다 (DB에 실제로 뭐가 저장됐는지 확인용)"""
    async with session_factory() as session:
        return await session.get(ReservationModel, reservation_id)


async def open_connections(session_factory, count: int) -> None:
    """DB 연결을 미리 count개 열어 둔다 (끝나면 연결 묶음에 남아 있다).
    새 연결을 여는 데 시간이 걸려서(윈도우에서 약 2초), 미리 안 열면 먼저 출발한 요청이
    commit까지 끝낸 뒤에야 다음 요청이 시작돼서 동시에 부딪치지 않는다."""
    sessions = [session_factory() for _ in range(count)]
    await asyncio.gather(*(s.execute(text("SELECT 1")) for s in sessions))
    for s in sessions:
        await s.close()


async def read_slot(session_factory, slot_id: int) -> tuple[int, int]:
    """새 연결로 (슬롯의 예약 인원, 확정 예약 건수)를 읽는다. commit된 것만 보인다"""
    async with session_factory() as session:
        reserved = await session.scalar(
            select(ReservationSlotModel.reserved_guests).where(
                ReservationSlotModel.id == slot_id
            )
        )
        confirmed = await session.scalar(
            select(func.count())
            .select_from(ReservationModel)
            .where(
                ReservationModel.slot_id == slot_id,
                ReservationModel.status == "CONFIRMED",
            )
        )
        return reserved, confirmed


async def delete_restaurant_of(session_factory, owner_id: uuid.UUID) -> None:
    """식당을 삭제된 상태로 만든다 (소프트 삭제: deleted_at만 채움)"""
    async with session_factory() as session:
        await session.execute(
            update(RestaurantModel)
            .where(RestaurantModel.owner_id == owner_id)
            .values(deleted_at=NOW)
        )
        await session.commit()


async def test_create_saves_reservation_and_increases_seats(session_factory):
    slot_id, _ = await add_slot(session_factory, capacity=10)
    user_id = await add_user(session_factory)

    await reserve(session_factory, user_id, slot_id, party_size=2)

    # commit까지 끝나서, 새 연결로 읽어도 자리 2명과 확정 예약 1건이 보인다.
    assert await read_slot(session_factory, slot_id) == (2, 1)


async def test_create_on_full_slot_raises_sold_out(session_factory):
    slot_id, _ = await add_slot(session_factory, capacity=10, reserved_guests=10)
    user_id = await add_user(session_factory)

    with pytest.raises(SlotSoldOut):
        await reserve(session_factory, user_id, slot_id, party_size=2)

    # 실패하면 commit하지 않아서 자리도 예약도 그대로다.
    assert await read_slot(session_factory, slot_id) == (10, 0)


async def test_five_requests_for_last_seats_only_one_succeeds(session_factory):
    # 남은 자리 2개에 다섯 사람이 2명씩 동시에 예약한다
    slot_id, _ = await add_slot(session_factory, capacity=2)
    users = [await add_user(session_factory) for _ in range(5)]
    await open_connections(session_factory, 5)  # 다섯 요청이 정말 동시에 부딪치게

    results = await asyncio.gather(
        *(reserve(session_factory, user, slot_id, party_size=2) for user in users),
        return_exceptions=True,
    )

    # 슬롯 행 락 때문에 뒤 요청들은 앞 요청의 commit을 기다렸다가 "자리 없음"을 본다.
    failures = [r for r in results if isinstance(r, Exception)]
    assert len(failures) == 4
    assert all(isinstance(f, SlotSoldOut) for f in failures)
    # 자리는 정원(2명)을 넘지 않고, 확정 예약도 1건만 남는다.
    assert await read_slot(session_factory, slot_id) == (2, 1)


async def test_cancel_twice_releases_seats_only_once(session_factory):
    slot_id, _ = await add_slot(session_factory, capacity=10)
    user_id = await add_user(session_factory)
    me = Actor(user_id=user_id, role=ActorRole.CUSTOMER)
    created, _ = await reserve(session_factory, user_id, slot_id, party_size=2)

    await cancel(session_factory, me, created.id)
    with pytest.raises(AlreadyCancelledError):
        await cancel(session_factory, me, created.id)

    # 두 번째 취소는 409이고, 자리는 한 번만 돌아와 0명이다.
    assert await read_slot(session_factory, slot_id) == (0, 0)


async def test_two_cancels_at_once_release_seats_only_once(session_factory):
    # 같은 예약을 동시에 두 번 취소해도(더블 클릭) 자리는 한 번만 돌아온다
    slot_id, _ = await add_slot(session_factory, capacity=10)
    user_id = await add_user(session_factory)
    me = Actor(user_id=user_id, role=ActorRole.CUSTOMER)
    created, _ = await reserve(session_factory, user_id, slot_id, party_size=2)
    await open_connections(session_factory, 2)  # 두 취소가 정말 동시에 부딪치게

    results = await asyncio.gather(
        cancel(session_factory, me, created.id),
        cancel(session_factory, me, created.id),
        return_exceptions=True,
    )

    failures = [r for r in results if isinstance(r, Exception)]
    assert len(failures) == 1
    assert isinstance(failures[0], AlreadyCancelledError)
    assert await read_slot(session_factory, slot_id) == (0, 0)


async def test_owner_cancels_reservation_of_own_restaurant(session_factory):
    slot_id, owner_id = await add_slot(session_factory, capacity=10)
    user_id = await add_user(session_factory)
    created, _ = await reserve(session_factory, user_id, slot_id, party_size=2)
    owner = Actor(user_id=owner_id, role=ActorRole.OWNER)

    await cancel(
        session_factory,
        owner,
        created.id,
        by=CancelledBy.OWNER,
        reason=CancelReason.PHONE_REQUEST,
    )

    # 그 식당 운영자가 취소하면 진짜 DB에도 취소가 저장되고 자리가 돌아온다.
    assert await read_slot(session_factory, slot_id) == (0, 0)


async def test_same_user_double_booking_at_once_keeps_one(session_factory):
    # 같은 사람이 같은 슬롯을 동시에 두 번 예약해도(더블 클릭) 확정 예약은 1건만 남는다
    slot_id, _ = await add_slot(session_factory, capacity=10)
    user_id = await add_user(session_factory)
    await open_connections(session_factory, 2)  # 두 요청이 정말 동시에 부딪치게

    results = await asyncio.gather(
        reserve(session_factory, user_id, slot_id, party_size=2),
        reserve(session_factory, user_id, slot_id, party_size=2),
        return_exceptions=True,
    )

    # 뒤 요청은 슬롯 잠금에서 기다렸다가 앞 예약을 보고 409 중복 예약이 된다.
    failures = [r for r in results if isinstance(r, Exception)]
    assert len(failures) == 1
    assert isinstance(failures[0], DuplicateReservationError)
    # 자리도 한 번만 늘어난다.
    assert await read_slot(session_factory, slot_id) == (2, 1)


async def test_db_index_blocks_second_confirmed_for_same_user_slot(session_factory):
    # 매니저를 거치지 않고 창고에 바로 넣어도, DB 부분 unique 인덱스가 두 번째 확정 예약을 막는다
    slot_id, _ = await add_slot(session_factory, capacity=10)
    user_id = await add_user(session_factory)

    async with session_factory() as session:
        repo = SQLAlchemyReservationRepository(session)
        await repo.add(
            Reservation.create(user_id=user_id, slot_id=slot_id, party_size=2, now=NOW)
        )
        await session.commit()

    async with session_factory() as session:
        repo = SQLAlchemyReservationRepository(session)
        with pytest.raises(ConflictError):
            await repo.add(
                Reservation.create(
                    user_id=user_id, slot_id=slot_id, party_size=2, now=NOW
                )
            )


async def test_admin_cancels_any_reservation(session_factory):
    slot_id, _ = await add_slot(session_factory, capacity=10)
    user_id = await add_user(session_factory)
    created, _ = await reserve(session_factory, user_id, slot_id, party_size=2)
    admin = Actor(user_id=uuid.uuid4(), role=ActorRole.ADMIN)

    await cancel(
        session_factory,
        admin,
        created.id,
        by=CancelledBy.ADMIN,
        reason=CancelReason.OTHER,
        note="관리자 정리",
    )

    # 관리자가 취소하면 진짜 DB에도 취소가 저장되고 자리가 돌아온다.
    assert await read_slot(session_factory, slot_id) == (0, 0)


async def test_other_owner_cancel_is_not_found(session_factory):
    slot_id, _ = await add_slot(session_factory, capacity=10)
    user_id = await add_user(session_factory)
    created, _ = await reserve(session_factory, user_id, slot_id, party_size=2)
    other_owner = Actor(
        user_id=await add_user(session_factory, role="OWNER"), role=ActorRole.OWNER
    )

    with pytest.raises(NotFoundError):
        await cancel(
            session_factory,
            other_owner,
            created.id,
            by=CancelledBy.OWNER,
            reason=CancelReason.PHONE_REQUEST,
        )

    # 다른 식당 운영자는 404로 막히고, 예약과 자리는 그대로다.
    assert await read_slot(session_factory, slot_id) == (2, 1)


async def test_deleted_restaurant_owner_cannot_cancel_but_admin_can(session_factory):
    slot_id, owner_id = await add_slot(session_factory, capacity=10)
    user_id = await add_user(session_factory)
    created, _ = await reserve(session_factory, user_id, slot_id, party_size=2)
    await delete_restaurant_of(session_factory, owner_id)
    owner = Actor(user_id=owner_id, role=ActorRole.OWNER)
    admin = Actor(user_id=uuid.uuid4(), role=ActorRole.ADMIN)

    # 식당이 삭제되면 식당 주인을 못 찾아서(삭제된 식당은 안 꺼냄), 운영자는 404다.
    with pytest.raises(NotFoundError):
        await cancel(
            session_factory,
            owner,
            created.id,
            by=CancelledBy.OWNER,
            reason=CancelReason.PHONE_REQUEST,
        )
    assert await read_slot(session_factory, slot_id) == (2, 1)

    # 관리자는 식당을 보지 않아서 그래도 취소할 수 있다.
    await cancel(
        session_factory,
        admin,
        created.id,
        by=CancelledBy.ADMIN,
        reason=CancelReason.OTHER,
        note="관리자 정리",
    )
    assert await read_slot(session_factory, slot_id) == (0, 0)


async def test_contact_phone_is_saved_in_one_shape(session_factory):
    slot_id, _ = await add_slot(session_factory, capacity=10)
    user_id = await add_user(session_factory)

    created, _ = await reserve(
        session_factory, user_id, slot_id, party_size=2, contact_phone="01012345678"
    )

    # 하이픈 없이 보내도 DB에는 010-1234-5678 모양으로 저장된다.
    async with session_factory() as session:
        saved = await session.scalar(
            select(ReservationModel.contact_phone).where(
                ReservationModel.id == created.id
            )
        )
    assert saved == "010-1234-5678"


async def test_owner_no_show_is_saved_and_keeps_seats(session_factory):
    slot_id, owner_id = await add_slot(session_factory, capacity=10)
    user_id = await add_user(session_factory)
    created, _ = await reserve(session_factory, user_id, slot_id, party_size=2)
    owner = Actor(user_id=owner_id, role=ActorRole.OWNER)

    await cancel(
        session_factory,
        owner,
        created.id,
        now=STARTS_AT + GRACE,
        by=CancelledBy.OWNER,
        reason=CancelReason.NO_SHOW,
    )

    # 노쇼는 상태 CANCELLED + 이유 NO_SHOW로 저장되고, 이미 지난 자리라 좌석은 그대로 2명이다.
    saved = await read_reservation(session_factory, created.id)
    assert saved.status == "CANCELLED"
    assert saved.cancelled_by == "OWNER"
    assert saved.cancel_reason == "NO_SHOW"
    reserved, _ = await read_slot(session_factory, slot_id)
    assert reserved == 2


async def test_check_in_is_saved_and_blocks_no_show(session_factory):
    slot_id, owner_id = await add_slot(session_factory, capacity=10)
    user_id = await add_user(session_factory)
    created, _ = await reserve(session_factory, user_id, slot_id, party_size=2)
    owner = Actor(user_id=owner_id, role=ActorRole.OWNER)

    async with session_factory() as session:
        await make_service(session).check_in(
            user=owner, reservation_id=created.id, now=STARTS_AT
        )

    # 입장 시각이 진짜 DB에 저장되고, 그 예약은 노쇼로 처리할 수 없다.
    saved = await read_reservation(session_factory, created.id)
    assert saved.checked_in_at == STARTS_AT
    with pytest.raises(AlreadyCheckedInError):
        await cancel(
            session_factory,
            owner,
            created.id,
            now=STARTS_AT + GRACE,
            by=CancelledBy.OWNER,
            reason=CancelReason.NO_SHOW,
        )


async def test_admin_cancel_note_is_saved(session_factory):
    slot_id, _ = await add_slot(session_factory, capacity=10)
    user_id = await add_user(session_factory)
    created, _ = await reserve(session_factory, user_id, slot_id, party_size=2)
    admin = Actor(user_id=uuid.uuid4(), role=ActorRole.ADMIN)

    await cancel(
        session_factory,
        admin,
        created.id,
        by=CancelledBy.ADMIN,
        reason=CancelReason.SYSTEM_ERROR,
        note="중복 결제 정리",
    )

    saved = await read_reservation(session_factory, created.id)
    assert saved.cancelled_by == "ADMIN"
    assert saved.cancel_reason == "SYSTEM_ERROR"
    assert saved.cancel_note == "중복 결제 정리"


async def test_restaurant_owner_of_query(session_factory):
    slot_id, owner_id = await add_slot(session_factory, capacity=10)
    user_id = await add_user(session_factory)
    created, _ = await reserve(session_factory, user_id, slot_id, party_size=2)

    # 예약 -> 슬롯 -> 식당을 이어서 주인 id를 꺼낸다. 없는 예약·삭제된 식당은 None
    async with session_factory() as session:
        repo = SQLAlchemyReservationRepository(session)
        assert await repo.restaurant_owner_of(created.id) == owner_id
        assert await repo.restaurant_owner_of(999) is None

    await delete_restaurant_of(session_factory, owner_id)
    async with session_factory() as session:
        repo = SQLAlchemyReservationRepository(session)
        assert await repo.restaurant_owner_of(created.id) is None


async def test_expire_no_shows_on_real_db(session_factory):
    slot_id, owner_id = await add_slot(session_factory, capacity=10)
    no_show_user = await add_user(session_factory)
    came_user = await add_user(session_factory)
    cancelled_user = await add_user(session_factory)
    no_show, _ = await reserve(session_factory, no_show_user, slot_id, party_size=2)
    came, _ = await reserve(session_factory, came_user, slot_id, party_size=2)
    cancelled, _ = await reserve(session_factory, cancelled_user, slot_id, party_size=2)
    owner = Actor(user_id=owner_id, role=ActorRole.OWNER)
    async with session_factory() as session:
        await make_service(session).check_in(
            user=owner, reservation_id=came.id, now=STARTS_AT
        )
    await cancel(
        session_factory,
        Actor(user_id=cancelled_user, role=ActorRole.CUSTOMER),
        cancelled.id,
    )

    # 15분 전에는 대상이 없고, 15분이 지나면 입장 안 한 확정 예약 1건만 찾는다
    async with session_factory() as session:
        repo = SQLAlchemyReservationRepository(session)
        assert (
            await repo.list_no_show_ids(STARTS_AT + GRACE - timedelta(seconds=1), GRACE)
            == []
        )
        assert await repo.list_no_show_ids(STARTS_AT + GRACE, GRACE) == [no_show.id]

    async with session_factory() as session:
        handled = await make_service(session).expire_no_shows(STARTS_AT + GRACE)

    assert handled == 1
    saved = await read_reservation(session_factory, no_show.id)
    assert saved.cancelled_by == "SYSTEM"
    assert saved.cancel_reason == "NO_SHOW"
    assert (await read_reservation(session_factory, came.id)).status == "CONFIRMED"
    # 좌석: 6명 예약 - 손님 취소 2명(시작 전이라 반납) = 4명, 노쇼 2명은 반납 안 함
    reserved, _ = await read_slot(session_factory, slot_id)
    assert reserved == 4


async def test_expire_no_shows_once_uses_container_wiring(session_factory):
    # 자동 반복이 부르는 container.expire_no_shows_once가 진짜 DB에서 노쇼를 처리하는지
    slot_id, _ = await add_slot(session_factory, capacity=10)
    user_id = await add_user(session_factory)
    created, _ = await reserve(session_factory, user_id, slot_id, party_size=2)

    handled = await expire_no_shows_once(session_factory, STARTS_AT + GRACE)

    assert handled == 1
    saved = await read_reservation(session_factory, created.id)
    assert saved.cancelled_by == "SYSTEM"
    assert saved.cancel_reason == "NO_SHOW"


async def test_owner_no_show_and_auto_no_show_at_once_handle_once(session_factory):
    # 운영자 노쇼 버튼과 자동 노쇼가 같은 순간에 와도 한 번만 처리되고, 좌석은 그대로다
    slot_id, owner_id = await add_slot(session_factory, capacity=10)
    user_id = await add_user(session_factory)
    created, _ = await reserve(session_factory, user_id, slot_id, party_size=2)
    owner = Actor(user_id=owner_id, role=ActorRole.OWNER)
    await open_connections(session_factory, 2)

    results = await asyncio.gather(
        cancel(
            session_factory,
            owner,
            created.id,
            now=STARTS_AT + GRACE,
            by=CancelledBy.OWNER,
            reason=CancelReason.NO_SHOW,
        ),
        expire_no_shows_once(session_factory, STARTS_AT + GRACE),
        return_exceptions=True,
    )

    owner_result, auto_handled = results
    # 운영자가 이기면 자동은 0건(건너뜀), 자동이 이기면 운영자는 409(이미 취소됨)
    if isinstance(owner_result, Exception):
        assert isinstance(owner_result, AlreadyCancelledError)
        assert auto_handled == 1
    else:
        assert auto_handled == 0
    saved = await read_reservation(session_factory, created.id)
    assert saved.cancel_reason == "NO_SHOW"
    reserved, _ = await read_slot(session_factory, slot_id)
    assert reserved == 2


async def test_two_auto_no_show_runs_at_once_handle_once(session_factory):
    # 서버가 두 대라 자동 노쇼가 동시에 두 번 돌아도, 예약마다 한 번만 처리된다
    slot_id, _ = await add_slot(session_factory, capacity=10)
    users = [await add_user(session_factory) for _ in range(3)]
    for user in users:
        await reserve(session_factory, user, slot_id, party_size=2)
    await open_connections(session_factory, 2)

    handled = await asyncio.gather(
        expire_no_shows_once(session_factory, STARTS_AT + GRACE),
        expire_no_shows_once(session_factory, STARTS_AT + GRACE),
    )

    assert sum(handled) == 3  # 3건을 두 번 처리하지 않고 합쳐서 3건
    reserved, confirmed = await read_slot(session_factory, slot_id)
    assert confirmed == 0
    assert reserved == 6  # 노쇼는 좌석을 안 돌려준다


async def test_check_in_and_auto_no_show_at_once_never_both(session_factory):
    # 입장 확인과 자동 노쇼가 동시에 와도 둘 중 하나만 된다 (입장했는데 노쇼인 예약은 없다)
    slot_id, owner_id = await add_slot(session_factory, capacity=10)
    user_id = await add_user(session_factory)
    created, _ = await reserve(session_factory, user_id, slot_id, party_size=2)
    owner = Actor(user_id=owner_id, role=ActorRole.OWNER)
    await open_connections(session_factory, 2)

    async def check_in():
        async with session_factory() as session:
            return await make_service(session).check_in(
                user=owner, reservation_id=created.id, now=STARTS_AT + GRACE
            )

    check_in_result, auto_handled = await asyncio.gather(
        check_in(),
        expire_no_shows_once(session_factory, STARTS_AT + GRACE),
        return_exceptions=True,
    )

    saved = await read_reservation(session_factory, created.id)
    if isinstance(check_in_result, Exception):
        # 자동 노쇼가 먼저: 입장 확인은 이미 취소된 예약이라 409, 입장 기록 없음
        assert isinstance(check_in_result, AlreadyCancelledError)
        assert auto_handled == 1
        assert saved.status == "CANCELLED" and saved.checked_in_at is None
    else:
        # 입장 확인이 먼저: 자동 노쇼는 건너뜀, 확정 + 입장 기록 있음
        assert auto_handled == 0
        assert saved.status == "CONFIRMED" and saved.checked_in_at is not None


async def test_hundred_requests_on_one_slot_load(session_factory):
    # 부하: 정원 10명 슬롯에 100명이 1명씩 동시에 예약한다 (앱과 같은 연결 묶음: 기본 15개)
    slot_id, _ = await add_slot(session_factory, capacity=10)
    other_slot_id, _ = await add_slot(
        session_factory, capacity=10
    )  # 상관없는 다른 슬롯
    users = [await add_user(session_factory) for _ in range(100)]
    other_user = await add_user(session_factory)
    await open_connections(session_factory, 15)  # 연결 묶음을 미리 다 열어 둔다

    async def timed(coro):
        started = time.perf_counter()
        try:
            return await coro, time.perf_counter() - started
        except Exception as error:  # noqa: BLE001 - 실패도 걸린 시간과 같이 모아서 아래에서 종류를 검사한다
            return error, time.perf_counter() - started

    started = time.perf_counter()
    results = await asyncio.gather(
        *(
            timed(reserve(session_factory, user, slot_id, party_size=1))
            for user in users
        ),
        timed(reserve(session_factory, other_user, other_slot_id, party_size=1)),
    )
    total = time.perf_counter() - started

    *crowd, (other_result, other_seconds) = results
    successes = [r for r, _ in crowd if not isinstance(r, Exception)]
    sold_out = [r for r, _ in crowd if isinstance(r, SlotSoldOut)]
    unexpected = [
        r
        for r, _ in crowd
        if isinstance(r, Exception) and not isinstance(r, SlotSoldOut)
    ]
    slowest = max(seconds for _, seconds in crowd)
    print(
        f"\n[부하] 100명 동시 예약: 전체 {total:.2f}초, 가장 늦은 요청 {slowest:.2f}초, "
        f"성공 {len(successes)}, 자리 없음 {len(sold_out)}, 그 밖의 에러 {len(unexpected)}, "
        f"다른 슬롯 예약 {other_seconds:.2f}초"
    )

    # 정확히 정원(10명)만 성공하고, 나머지 90명은 409 자리 없음이다. 500(그 밖의 에러)은 0개
    assert len(successes) == 10
    assert len(sold_out) == 90
    assert unexpected == []
    assert await read_slot(session_factory, slot_id) == (10, 10)
    # 몰린 슬롯 때문에 다른 슬롯 예약이 실패하지 않는다 (연결 대기 30초 안에 끝남)
    assert not isinstance(other_result, Exception)
    assert slowest < 30


async def hold_slot_lock(session, slot_id: int) -> None:
    """슬롯 줄을 FOR UPDATE로 잠그고 commit하지 않는다 (앞 요청이 멈춘 상황 흉내)"""
    await session.execute(
        select(ReservationSlotModel.id)
        .where(ReservationSlotModel.id == slot_id)
        .with_for_update()
    )


async def test_waiting_request_gives_up_after_lock_timeout(session_factory):
    # 앞 요청(A)이 슬롯을 잠근 채 멈추면, 뒤 요청(B)은 락 대기 시간(0.5초)만 기다리고 409로 끝난다
    slot_id, _ = await add_slot(session_factory, capacity=10)
    user_id = await add_user(session_factory)
    await open_connections(
        session_factory, 2
    )  # 연결 여는 시간이 기다린 시간에 섞이지 않게

    async with session_factory() as holder:
        await hold_slot_lock(holder, slot_id)
        started = time.perf_counter()
        with pytest.raises(ReservationBusyError):
            await reserve(
                session_factory,
                user_id,
                slot_id,
                party_size=2,
                time_limits=SHORT_LIMITS,
            )
        waited = time.perf_counter() - started

        # A는 피해가 없다: B가 포기한 뒤에도 A는 그대로 저장하고 commit할 수 있다
        await holder.execute(
            update(ReservationSlotModel)
            .where(ReservationSlotModel.id == slot_id)
            .values(reserved_guests=1)
        )
        await holder.commit()

    # 0.5초는 기다렸고(바로 튕긴 게 아님), 끝없이 기다리지도 않았다
    assert 0.4 <= waited < 1.5
    # B는 rollback돼서 예약이 생기지 않았고, 자리는 A가 고친 값 그대로다
    assert await read_slot(session_factory, slot_id) == (1, 0)


async def test_stalled_holder_is_cut_and_lock_released(session_factory):
    # 잠근 요청이 파이썬 쪽에서 멈춰 명령을 안 보내면(1초), DB가 그 세션을 끊어 잠금을 풀어 준다
    slot_id, _ = await add_slot(session_factory, capacity=10)
    user_id = await add_user(session_factory)
    await open_connections(session_factory, 2)

    async with session_factory() as holder:
        await SQLAlchemyReservationRepository(holder, SHORT_LIMITS).set_time_limits()
        await hold_slot_lock(holder, slot_id)
        await asyncio.sleep(1.5)  # 멈춘 트랜잭션 제한(1초)보다 오래 아무것도 안 함

        # 다른 요청은 기다리지 않고 바로 예약된다 (잠금이 이미 풀림)
        started = time.perf_counter()
        await reserve(session_factory, user_id, slot_id, party_size=2)
        assert time.perf_counter() - started < 1

        # 끊긴 세션으로 다시 명령하면 "연결이 끊겼다"는 DB 오류가 난다. A는 이미 멈춘(고장 난) 요청이라 실패가 맞다
        # (DB가 세션을 끊을 때 오류 코드 25P03을 돌려주지 못하고 연결만 닫아서, 예약 에러로 바뀌지는 않는다)
        with pytest.raises(DBAPIError):
            await holder.execute(text("SELECT 1"))

    assert await read_slot(session_factory, slot_id) == (2, 1)


async def test_slow_statement_is_cancelled_as_timeout(session_factory):
    # 쿼리 하나가 쿼리 제한(1초)보다 오래 걸리면 DB가 취소하고, 시간 초과 에러(503)로 바뀐다
    async with session_factory() as session:
        await SQLAlchemyReservationRepository(session, SHORT_LIMITS).set_time_limits()
        started = time.perf_counter()
        with pytest.raises(ReservationTimeoutError):
            await session.execute(text("SELECT pg_sleep(3)"))
        elapsed = time.perf_counter() - started

    assert elapsed < 2  # 3초를 다 기다리지 않고 1초쯤에 끊겼다


async def test_time_limits_end_with_transaction(session_factory):
    # 시간 제한은 그 트랜잭션에만 걸린다 (SET LOCAL). commit 뒤 같은 연결을 다른 기능이 써도 제한이 없다
    slot_id, _ = await add_slot(session_factory, capacity=10)
    user_id = await add_user(session_factory)
    engine = session_factory.kw["bind"]

    async with engine.connect() as conn:  # 연결 하나를 붙잡아 두고 그 위에서 예약한다
        session = AsyncSession(bind=conn, expire_on_commit=False)
        await make_service(session).create(
            user_id=user_id, slot_id=slot_id, party_size=2, contact_phone=None, now=NOW
        )
        settings = [
            (await conn.execute(text(f"SHOW {name}"))).scalar_one()
            for name in (
                "lock_timeout",
                "statement_timeout",
                "idle_in_transaction_session_timeout",
            )
        ]
        await session.close()

    # 예약 트랜잭션이 끝나자 원래 값(0 = 이 연결의 기본값)으로 돌아왔다
    assert settings == ["0", "0", "0"]
    assert await read_slot(session_factory, slot_id) == (2, 1)
