# [담당 5 최지훈] 예약 상세 매니저 테스트: 본인,식당 운영자만 / 나머지는 404
import uuid
from datetime import datetime, timezone

import pytest

from auth.domain.value_object import AuthenticatedUser, AuthRole # 담당1 로그인
from common.errors import NotFoundError # 공통오류
from reservation.application.query_service import ReservationQueryService # 담당5 시험할 매니저
from reservation.domain.reservation import Reservation, ReservationStatus # 담당4 예약
from slot.domain.time_slot import TimeSlot # 담당3 슬롯

ME = AuthenticatedUser(user_id=uuid.uuid4(), role=AuthRole.CUSTOMER) # 예약한 본인
OWNER = AuthenticatedUser(user_id=uuid.uuid4(), role=AuthRole.OWNER) # 식당주인
STRANGER = AuthenticatedUser(user_id=uuid.uuid4(), role=AuthRole.CUSTOMER) # 관계없는 다른

SLOT = TimeSlot(
    id=10,
    restaurant_id=1,
    starts_at=datetime(2026, 11, 20, 9, 0, tzinfo=timezone.utc),
    ends_at=datetime(2026, 11, 20, 10, 30, tzinfo=timezone.utc),
    capacity=20,
    reserved_guests=2,
    max_party_size=4,
)

RESERVATION = Reservation(
    id=100,
    user_id=ME.user_id,                        # 누가 예약했나? (본인)
    slot_id=SLOT.id,
    party_size=2,
    status=ReservationStatus.CONFIRMED,
    created_at=datetime(2026, 11, 6, 3, 0, tzinfo=timezone.utc),
)

class FakeReservationQueryRepository:
    """DB 없이 정해 진 값만 돌려주는 가짜 창고"""
    async def get_reservation(self, reservation_id): # 100번이면 (예약, 슬롯, 주인번호), 아니면 None
        if reservation_id == RESERVATION.id:
            return RESERVATION, SLOT, OWNER.user_id
        return None


async def test_me_can_see_my_reservation(): # 내 예약 상세 확인 통과
    service = ReservationQueryService(db=None)
    service.query = FakeReservationQueryRepository() # 가짜 창고 만들어 끼우기

    reservation, slot = await service.get_reservation(ME, RESERVATION.id)   # 누가? 본인

    assert reservation == RESERVATION
    assert slot == SLOT



async def test_owner_can_see_reservation_of_my_restaurant(): # 내 식당 예약 상세 확인 통과
    service = ReservationQueryService(db=None)
    service.query = FakeReservationQueryRepository()

    reservation, slot = await service.get_reservation(OWNER, RESERVATION.id)   # 누가? 식당 주인

    assert reservation == RESERVATION
    assert slot == SLOT


async def test_stranger_gets_404(): # 남의 예약 상세 확인 404 (403 아님: 있다는 것도 숨김)
    service = ReservationQueryService(db=None)
    service.query = FakeReservationQueryRepository()

    with pytest.raises(NotFoundError):
        await service.get_reservation(STRANGER, RESERVATION.id)


async def test_missing_reservation_gets_404(): # 없는 예약 상세 확인 404
    service = ReservationQueryService(db=None)
    service.query = FakeReservationQueryRepository()

    with pytest.raises(NotFoundError):
        await service.get_reservation(ME, 555)