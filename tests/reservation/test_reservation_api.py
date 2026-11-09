# [담당 4] 예약 창구 테스트 : 가짜 매니저로 예약 취소 API의 요청.응답 확인
import uuid
from datetime import datetime

import httpx
from fastapi import FastAPI

from auth.domain.value_object import AuthenticatedUser, AuthRole
from auth.presentation.dependencies import get_authenticated_user
from common.error_handlers import register_error_handlers
from common.schemas import SEOUL
from container import create_reservation_service
from reservation.domain.exceptions import AlreadyCancelledError
from reservation.domain.reservation import Reservation, ReservationStatus
from reservation.presentation.router import router
from slot.domain.time_slot import TimeSlot

USER_ID = uuid.UUID("00000000-0000-4000-8000-000000000001")
CREATED_AT = datetime(2026, 12, 1, 15, 0, tzinfo=SEOUL)
CANCELLED_AT = datetime(2026, 12, 3, 17, 0, tzinfo=SEOUL)
STARTS_AT = datetime(2026, 12, 3, 18, 0, tzinfo=SEOUL)
ENDS_AT = datetime(2026, 12, 3, 19, 0, tzinfo=SEOUL)

ME = AuthenticatedUser(user_id=USER_ID, role=AuthRole.CUSTOMER)

# 취소가 끝난 뒤의 슬롯 : 2명을 돌려줘서 0명
SLOT = TimeSlot(
    id=7,
    restaurant_id=1,
    starts_at=STARTS_AT,
    ends_at=ENDS_AT,
    capacity=10,
    reserved_guests=0,
    max_party_size=4,
)

# 취소가 끝난 뒤의 예약
CANCELLED = Reservation(
    id=15,
    user_id=USER_ID,
    slot_id=7,
    party_size=2,
    status=ReservationStatus.CANCELLED,
    created_at=CREATED_AT,
    cancelled_at=CANCELLED_AT,
)


class FakeReservationService:
    """정해진 결과만 돌려주는 가짜 예약 매니저"""

    def __init__(self, error: Exception | None = None) -> None:
        self.cancel_calls: list[
            tuple[uuid.UUID, int]
        ] = []  # 창구가 넘긴 값을 적는 기록장
        self.error = error  # 넣어 주면 cancel에서 이 에러를 던진다

    async def cancel(
        self, user_id: uuid.UUID, reservation_id: int, now: datetime
    ) -> tuple[Reservation, TimeSlot]:
        self.cancel_calls.append((user_id, reservation_id))
        if self.error:
            raise self.error  # 진짜 서비스가 도메인 규칙에 걸려 에러를 던지는 흉내
        return CANCELLED, SLOT


def make_client(fake_service: FakeReservationService) -> httpx.AsyncClient:
    """예약 창구만 단 작은 앱을 만들고, 로그인과 매니저를 가짜로 바꾼다"""
    app = FastAPI()
    register_error_handlers(app)
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[get_authenticated_user] = lambda: ME  # 로그인한 사람은 나
    app.dependency_overrides[create_reservation_service] = lambda: (
        fake_service
    )  # 테스트에서 기록장을 봐야 해서 만든 객체 그대로
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    )


async def test_cancel_returns_cancelled_reservation():
    fake = FakeReservationService()

    async with make_client(fake) as client:
        response = await client.post("/api/v1/reservations/15/cancel")

    # 200과 함께 취소된 예약이 응답 모양(ReservationOut)으로 온다.
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["id"] == 15
    assert data["status"] == "CANCELLED"
    # 이미 취소됐으니 또 취소할 수 없다.
    assert data["can_cancel"] is False
    # 창구는 로그인한 나와 주소의 15번을 매니저에게 넘긴다.
    assert fake.cancel_calls == [(USER_ID, 15)]


async def test_cancel_twice_returns_409():
    fake = FakeReservationService(error=AlreadyCancelledError())

    async with make_client(fake) as client:
        response = await client.post("/api/v1/reservations/15/cancel")

    # 매니저가 던진 에러가 공통 실패 봉투(409, ALREADY_CANCELLED)로 바뀐다.
    assert response.status_code == 409
    body = response.json()
    assert body["success"] is False
    assert body["code"] == "ALREADY_CANCELLED"


async def test_cancel_with_zero_id_returns_422():
    fake = FakeReservationService()

    async with make_client(fake) as client:
        response = await client.post("/api/v1/reservations/0/cancel")

    # 예약 번호가 0 이하면 매니저까지 가지 않고 422로 막힌다.
    assert response.status_code == 422
    assert fake.cancel_calls == []
