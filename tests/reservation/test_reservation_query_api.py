# [담당 5 최지훈] 내 예약 창구 테스트: 손님 본인이 예약 상세를 보면 200, 취소 가능
import uuid
from datetime import datetime, timezone

import httpx                                                               # 가짜 브라우저
from fastapi import FastAPI

from auth.domain.value_object import AuthenticatedUser, AuthRole           # 담당1 로그인한 사람
from auth.presentation.dependencies import get_authenticated_user          # 담당1 로그인 문지기 (가짜로 바꿀 것)
from common.error_handlers import register_error_handlers                  # 공통 오류 → 실패 봉투
from container import create_reservation_query_service                     # 담당5 매니저 공장 (가짜로 바꿀 것)
from reservation.presentation.query_router import router                   # 담당5 시험할 창구
from reservation.domain.reservation import Reservation, ReservationStatus  # 담당4 예약
from slot.domain.time_slot import TimeSlot                                 # 담당3 슬롯

CUSTOMER = AuthenticatedUser(user_id=uuid.uuid4(), role=AuthRole.CUSTOMER)

SLOT = TimeSlot(
    id=10,
    restaurant_id=1,
    starts_at=datetime(2030, 11, 20, 9, 0, tzinfo=timezone.utc),    # 먼 미래 → 늘 "시작 전"
    ends_at=datetime(2030, 11, 20, 10, 30, tzinfo=timezone.utc),
    capacity=20,
    reserved_guests=2,
    max_party_size=4,
)

RESERVATION = Reservation(
    id=100,
    user_id=CUSTOMER.user_id,                        # 누가 예약했나? (손님)
    slot_id=SLOT.id,
    party_size=2,
    status=ReservationStatus.CONFIRMED,
    created_at=datetime(2026, 11, 6, 3, 0, tzinfo=timezone.utc),
)


class FakeReservationQueryService:  # DB 없이 정해진 값만 돌려주는 가짜 매니저
    async def get_reservation(self, me, reservation_id):
        return RESERVATION, SLOT    # 예약 1건 (예약, 슬롯 짝)


def fake_login_customer():   # 가짜 로그인: 손님이 로그인한 척
    return CUSTOMER


def make_client(fake_login):
    """내 창구만 단 작은 앱 + 가짜 브라우저 만들기"""
    app = FastAPI()
    register_error_handlers(app)
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[get_authenticated_user] = fake_login      # 로그인 → 가짜
    app.dependency_overrides[create_reservation_query_service] = FakeReservationQueryService  # 매니저 → 가짜
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


async def test_customer_sees_own_reservation(): # 손님 본인 예약 상세 확인 200, 취소 가능
    async with make_client(fake_login_customer) as client:
        response = await client.get("/api/v1/reservations/100")   # 100번 예약 상세 요청

    assert response.status_code == 200
    data = response.json()["data"]                    # 상세는 하나라서 items 없이 바로
    assert data["id"] == 100                          # 100번 예약이 왔나
    assert data["can_cancel"] is True                 # 내 예약 + 시작 전 → 취소 가능


async def test_too_big_reservation_id_is_422(): # DB 번호 칸보다 큰 번호 확인 422 (500 아님)
    async with make_client(fake_login_customer) as client:
        response = await client.get(f"/api/v1/reservations/{10**19}")

    assert response.status_code == 422
