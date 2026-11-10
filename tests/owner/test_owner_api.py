# [담당 5 최지훈] 운영자 창구 테스트: 고객은 문지기에서 403, 운영자는 예약 목록·CSV 내려받기
import uuid
from datetime import datetime, timezone

import httpx                                                               # 가짜 브라우저
from fastapi import FastAPI

from auth.domain.value_object import AuthenticatedUser, AuthRole           # 담당1 로그인한 사람
from auth.presentation.dependencies import get_authenticated_user          # 담당1 로그인 문지기 (가짜로 바꿀 것)
from common.error_handlers import register_error_handlers                  # 공통 오류 → 실패 봉투
from container import create_owner_service                                 # 담당5 매니저 공장 (가짜로 바꿀 것)
from owner.presentation.router import router                               # 담당5 시험할 창구
from reservation.domain.reservation import Reservation, ReservationStatus  # 담당4 예약
from slot.domain.time_slot import TimeSlot                                 # 담당3 슬롯

OWNER = AuthenticatedUser(user_id=uuid.uuid4(), role=AuthRole.OWNER)
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


class FakeOwnerService:  # DB 없이 정해진 값만 돌려주는 가짜 매니저
    async def list_restaurant_reservations(self, owner, restaurant_id, day, page):
        return [(RESERVATION, SLOT)], 1    # 예약 1건 → 목록에 한 줄, 전체 1개

    async def export_restaurant_reservations(self, owner, restaurant_id, day):
        return []    # 예약 없음 → CSV는 머리 줄만


def fake_login_owner():      # 가짜 로그인: 운영자가 로그인한 척
    return OWNER


def fake_login_customer():   # 가짜 로그인: 손님이 로그인한 척
    return CUSTOMER


def make_client(fake_login):
    """내 창구만 단 작은 앱 + 가짜 브라우저 만들기"""
    app = FastAPI()
    register_error_handlers(app)
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[get_authenticated_user] = fake_login      # 로그인 → 가짜
    app.dependency_overrides[create_owner_service] = FakeOwnerService  # 매니저 → 가짜
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


async def test_customer_cannot_use_owner_api(): # 손님이 운영자 API 확인 403
    async with make_client(fake_login_customer) as client:
        response = await client.get("/api/v1/owner/restaurants")

    assert response.status_code == 403
    assert response.json()["success"] is False


async def test_owner_can_download_csv(): # 운영자 CSV 내려받기 확인 통과
    async with make_client(fake_login_owner) as client:
        response = await client.get("/api/v1/owner/restaurants/1/reservations/export/csv")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "reservations_1.csv" in response.headers["content-disposition"]
    assert "예약번호" in response.text


async def test_owner_sees_reservation_list(): # 운영자 예약 목록 확인 200, 손님 예약은 취소 불가
    async with make_client(fake_login_owner) as client:
        response = await client.get("/api/v1/owner/restaurants/1/reservations")

    assert response.status_code == 200
    item = response.json()["data"]["items"][0]        # 응답 봉투 → data → 목록 → 첫 번째
    assert item["id"] == 100                          # 100번 예약이 왔나
    assert item["can_cancel"] is False                # 남(손님)의 예약 → 운영자는 취소 불가


async def test_too_big_restaurant_id_is_422(): # DB 번호 칸보다 큰 식당 번호 확인 422 (500 아님)
    async with make_client(fake_login_owner) as client:
        listing = await client.get(f"/api/v1/owner/restaurants/{10**19}/reservations")
        csv_file = await client.get(f"/api/v1/owner/restaurants/{10**19}/reservations/export/csv")

    assert listing.status_code == 422
    assert csv_file.status_code == 422
