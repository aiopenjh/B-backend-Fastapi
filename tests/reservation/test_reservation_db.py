# [담당 4] 예약 실제 DB 테스트 : 진짜 PostgreSQL로 예약 생성, 꽉 찬 슬롯, 동시 예약, 취소 확인
import asyncio
import os
import uuid
from datetime import datetime

import pytest
from dotenv import load_dotenv
from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from auth.domain.value_object import AuthenticatedUser, AuthRole
from common.errors import NotFoundError
from common.model import Base, init_models
from common.schemas import SEOUL
from common.unit_of_work import ConflictError
from reservation.application.service import ReservationService
from reservation.domain.exceptions import (
    AlreadyCancelledError,
    DuplicateReservationError,
)
from reservation.domain.reservation import Reservation
from reservation.infrastructure.models import ReservationModel
from reservation.infrastructure.repositories import SQLAlchemyReservationRepository
from restaurant.application.service import RestaurantService
from restaurant.domain.exceptions import RestaurantNotFoundError
from restaurant.infrastructure.models import RestaurantModel
from restaurant.infrastructure.repository import RestaurantRepository
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


@pytest.fixture
async def session_factory():
    """테스트마다 표를 비우고 새로 만든 뒤, 끝나면 연결을 정리한다"""
    engine = create_async_engine(TEST_POSTGRES_URL)
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


def make_service(session) -> ReservationService:
    # 요청 하나 = 세션 하나. 앱의 create_reservation_service와 같은 조립
    uow = SQLAlchemyUnitOfWork(session)
    return ReservationService(
        reservation_repo=SQLAlchemyReservationRepository(session),
        slot_repo=SQLAlchemySlotRepository(session),
        restaurant_service=RestaurantService(
            repo=RestaurantRepository(session), uow=uow
        ),
        uow=uow,
    )


async def reserve(
    session_factory,
    user_id: uuid.UUID,
    slot_id: int,
    party_size: int,
    contact_phone: str | None = None,
):
    async with session_factory() as session:
        return await make_service(session).create(
            user_id=user_id,
            slot_id=slot_id,
            party_size=party_size,
            contact_phone=contact_phone,
            now=NOW,
        )


async def cancel(session_factory, user: AuthenticatedUser, reservation_id: int):
    async with session_factory() as session:
        return await make_service(session).cancel(
            user=user, reservation_id=reservation_id, now=NOW
        )


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
    me = AuthenticatedUser(user_id=user_id, role=AuthRole.CUSTOMER)
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
    me = AuthenticatedUser(user_id=user_id, role=AuthRole.CUSTOMER)
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
    owner = AuthenticatedUser(user_id=owner_id, role=AuthRole.OWNER)

    await cancel(session_factory, owner, created.id)

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
    admin = AuthenticatedUser(user_id=uuid.uuid4(), role=AuthRole.ADMIN)

    await cancel(session_factory, admin, created.id)

    # 관리자가 취소하면 진짜 DB에도 취소가 저장되고 자리가 돌아온다.
    assert await read_slot(session_factory, slot_id) == (0, 0)


async def test_other_owner_cancel_is_not_found(session_factory):
    slot_id, _ = await add_slot(session_factory, capacity=10)
    user_id = await add_user(session_factory)
    created, _ = await reserve(session_factory, user_id, slot_id, party_size=2)
    other_owner = AuthenticatedUser(
        user_id=await add_user(session_factory, role="OWNER"), role=AuthRole.OWNER
    )

    with pytest.raises(NotFoundError):
        await cancel(session_factory, other_owner, created.id)

    # 다른 식당 운영자는 404로 막히고, 예약과 자리는 그대로다.
    assert await read_slot(session_factory, slot_id) == (2, 1)


async def test_deleted_restaurant_owner_cannot_cancel_but_admin_can(session_factory):
    slot_id, owner_id = await add_slot(session_factory, capacity=10)
    user_id = await add_user(session_factory)
    created, _ = await reserve(session_factory, user_id, slot_id, party_size=2)
    await delete_restaurant_of(session_factory, owner_id)
    owner = AuthenticatedUser(user_id=owner_id, role=AuthRole.OWNER)
    admin = AuthenticatedUser(user_id=uuid.uuid4(), role=AuthRole.ADMIN)

    # 식당이 삭제되면 식당 창고가 식당을 안 꺼내서, 운영자는 404다.
    with pytest.raises(RestaurantNotFoundError):
        await cancel(session_factory, owner, created.id)
    assert await read_slot(session_factory, slot_id) == (2, 1)

    # 관리자는 식당을 보지 않아서 그래도 취소할 수 있다.
    await cancel(session_factory, admin, created.id)
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
