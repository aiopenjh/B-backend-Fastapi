# [담당 5 최지훈] 운영자 창구 테스트: 고객은 문지기에서 403, 운영자는 CSV 내려받기
import uuid

import httpx                                            # 가짜 브라우저
from fastapi import FastAPI

from auth.domain.value_object import AuthenticatedUser, AuthRole       # 담당1 로그인한 사람
from auth.presentation.dependencies import get_authenticated_user      # 담당1 로그인 문지기 (가짜로 바꿀 것)
from common.error_handlers import register_error_handlers              # 공통 오류 → 실패 봉투
from container import create_owner_service                             # 담당5 매니저 공장 (가짜로 바꿀 것)
from owner.presentation.router import router                           # 담당5 시험할 창구

OWNER = AuthenticatedUser(user_id=uuid.uuid4(), role=AuthRole.OWNER)
CUSTOMER = AuthenticatedUser(user_id=uuid.uuid4(), role=AuthRole.CUSTOMER)


class FakeOwnerService:
    """DB 없이 정해진 값만 돌려주는 가짜 매니저"""

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