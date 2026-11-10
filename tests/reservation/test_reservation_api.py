# [담당 4] 예약 창구 테스트 : 가짜 매니저로 예약 생성.취소 API의 요청.응답 확인
import uuid
from datetime import datetime

import httpx
from fastapi import FastAPI

from auth.domain.value_object import AuthenticatedUser, AuthRole
from auth.presentation.dependencies import get_authenticated_user
from common.error_handlers import register_error_handlers
from common.schemas import SEOUL
from container import create_reservation_service
from reservation.domain.exceptions import AlreadyCancelledError, NoShowTooEarlyError
from reservation.domain.reservation import (
    CancelledBy,
    CancelReason,
    Reservation,
    ReservationStatus,
)
from reservation.presentation.router import admin_router, owner_router, router
from slot.domain.exceptions import SlotSoldOut
from slot.domain.time_slot import TimeSlot

USER_ID = uuid.UUID("00000000-0000-4000-8000-000000000001")
CREATED_AT = datetime(2026, 12, 1, 15, 0, tzinfo=SEOUL)
CANCELLED_AT = datetime(2026, 12, 3, 17, 0, tzinfo=SEOUL)
STARTS_AT = datetime(2026, 12, 3, 18, 0, tzinfo=SEOUL)
ENDS_AT = datetime(2026, 12, 3, 19, 0, tzinfo=SEOUL)

ME = AuthenticatedUser(user_id=USER_ID, role=AuthRole.CUSTOMER)
OWNER = AuthenticatedUser(
    user_id=uuid.UUID("00000000-0000-4000-8000-000000000003"), role=AuthRole.OWNER
)
ADMIN = AuthenticatedUser(
    user_id=uuid.UUID("00000000-0000-4000-8000-000000000005"), role=AuthRole.ADMIN
)

# 7번 슬롯 (응답에는 식당 id와 시각만 쓰인다)
SLOT = TimeSlot(
    id=7,
    restaurant_id=1,
    starts_at=STARTS_AT,
    ends_at=ENDS_AT,
    capacity=10,
    reserved_guests=0,
    max_party_size=4,
)

# 방금 만든 확정 예약
CONFIRMED = Reservation(
    id=15,
    user_id=USER_ID,
    slot_id=7,
    party_size=2,
    contact_phone="010-1234-5678",
    status=ReservationStatus.CONFIRMED,
    created_at=CREATED_AT,
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
        self.create_calls: list[
            tuple[uuid.UUID, int, int, str | None]
        ] = []  # 생성 때 창구가 넘긴 값
        self.cancel_calls: list[tuple[uuid.UUID, int]] = []  # 취소 때 창구가 넘긴 값
        self.cancel_options: list[tuple] = []  # 취소 때 넘긴 (누가, 왜, 메모)
        self.check_in_calls: list[tuple[uuid.UUID, int]] = []  # 입장 확인 때 넘긴 값
        self.error = error  # 넣어 주면 생성.취소.입장 확인에서 이 에러를 던진다

    async def create(
        self,
        user_id: uuid.UUID,
        slot_id: int,
        party_size: int,
        contact_phone: str | None,
        now: datetime,
    ) -> tuple[Reservation, TimeSlot]:
        self.create_calls.append((user_id, slot_id, party_size, contact_phone))
        if self.error:
            raise self.error
        return CONFIRMED, SLOT

    async def cancel(
        self,
        user: AuthenticatedUser,
        reservation_id: int,
        now: datetime,
        by: CancelledBy = CancelledBy.CUSTOMER,
        reason: CancelReason = CancelReason.CUSTOMER_REQUEST,
        note: str | None = None,
    ) -> tuple[Reservation, TimeSlot]:
        self.cancel_calls.append((user.user_id, reservation_id))
        self.cancel_options.append((by, reason, note))
        if self.error:
            raise self.error  # 진짜 서비스가 도메인 규칙에 걸려 에러를 던지는 흉내
        return CANCELLED, SLOT

    async def check_in(
        self, user: AuthenticatedUser, reservation_id: int, now: datetime
    ) -> tuple[Reservation, TimeSlot]:
        self.check_in_calls.append((user.user_id, reservation_id))
        if self.error:
            raise self.error
        return CONFIRMED, SLOT


def make_client(
    fake_service: FakeReservationService,
    logged_in: bool = True,
    user: AuthenticatedUser = ME,
) -> httpx.AsyncClient:
    """예약 창구(손님·운영자·관리자)만 단 작은 앱을 만들고, 로그인과 매니저를 가짜로 바꾼다"""
    app = FastAPI()
    register_error_handlers(app)
    app.include_router(router, prefix="/api/v1")
    app.include_router(owner_router, prefix="/api/v1")
    app.include_router(admin_router, prefix="/api/v1")
    if logged_in:  # 로그인한 사람은 user (False면 진짜 문지기가 돌아서 토큰 없이는 401)
        app.dependency_overrides[get_authenticated_user] = lambda: user
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


async def test_create_returns_201_with_reservation():
    fake = FakeReservationService()

    async with make_client(fake) as client:
        response = await client.post(
            "/api/v1/reservations",
            json={"slot_id": 7, "party_size": 2, "contact_phone": "  010-1234-5678  "},
        )

    # 201과 함께 만든 예약이 응답 모양으로 온다.
    assert response.status_code == 201
    assert response.json()["message"] == "예약이 완료되었습니다."
    data = response.json()["data"]
    assert data["id"] == 15
    assert data["status"] == "CONFIRMED"
    # 창구는 로그인한 나와, 공백은 지운 연락처를 매니저에게 넘긴다.
    assert fake.create_calls == [(USER_ID, 7, 2, "010-1234-5678")]


async def test_create_sold_out_returns_409():
    fake = FakeReservationService(error=SlotSoldOut())

    async with make_client(fake) as client:
        response = await client.post(
            "/api/v1/reservations", json={"slot_id": 7, "party_size": 2}
        )

    # 매니저가 던진 자리 부족 에러가 공통 실패 봉투(409, SLOT_SOLD_OUT)로 바뀐다.
    assert response.status_code == 409
    body = response.json()
    assert body["success"] is False
    assert body["code"] == "SLOT_SOLD_OUT"


async def test_create_without_login_returns_401():
    fake = FakeReservationService()

    async with make_client(fake, logged_in=False) as client:
        response = await client.post(
            "/api/v1/reservations", json={"slot_id": 7, "party_size": 2}
        )

    # 토큰 없이 부르면 매니저까지 가지 않고 401로 막힌다.
    assert response.status_code == 401
    assert response.json()["code"] == "UNAUTHORIZED"
    assert fake.create_calls == []


async def test_cancel_without_login_returns_401():
    fake = FakeReservationService()

    async with make_client(fake, logged_in=False) as client:
        response = await client.post("/api/v1/reservations/15/cancel")

    # 토큰 없이 부르면 매니저까지 가지 않고 401로 막힌다.
    assert response.status_code == 401
    assert response.json()["code"] == "UNAUTHORIZED"
    assert fake.cancel_calls == []


async def test_cancel_with_too_big_id_returns_422():
    fake = FakeReservationService()

    async with make_client(fake) as client:
        response = await client.post("/api/v1/reservations/9223372036854775808/cancel")

    # DB(BIGINT)에 못 담는 번호면 DB 오류(500) 대신 422로 막힌다.
    assert response.status_code == 422
    assert fake.cancel_calls == []


async def test_create_with_true_slot_id_returns_422():
    fake = FakeReservationService()

    async with make_client(fake) as client:
        response = await client.post(
            "/api/v1/reservations", json={"slot_id": True, "party_size": 2}
        )

    # true를 1번 슬롯으로 바꾸지 않고, 매니저까지 가기 전에 422로 막힌다.
    assert response.status_code == 422
    assert fake.create_calls == []


async def test_owner_cancel_passes_reason_and_note():
    fake = FakeReservationService()

    async with make_client(fake, user=OWNER) as client:
        response = await client.post(
            "/api/v1/owner/reservations/15/cancel",
            json={"reason": "PHONE_REQUEST", "note": "  손님 전화  "},
        )

    # 운영자 창구는 누가=운영자, 이유·메모(공백 지움)를 매니저에게 넘긴다.
    assert response.status_code == 200
    assert fake.cancel_calls == [(OWNER.user_id, 15)]
    assert fake.cancel_options == [
        (CancelledBy.OWNER, CancelReason.PHONE_REQUEST, "손님 전화")
    ]


async def test_owner_no_show_too_early_returns_409():
    fake = FakeReservationService(error=NoShowTooEarlyError())

    async with make_client(fake, user=OWNER) as client:
        response = await client.post(
            "/api/v1/owner/reservations/15/cancel", json={"reason": "NO_SHOW"}
        )

    # 매니저가 던진 노쇼 시각 에러가 실패 봉투(409, NO_SHOW_TOO_EARLY)로 바뀐다.
    assert response.status_code == 409
    assert response.json()["code"] == "NO_SHOW_TOO_EARLY"


async def test_owner_check_in_returns_200():
    fake = FakeReservationService()

    async with make_client(fake, user=OWNER) as client:
        response = await client.post("/api/v1/owner/reservations/15/check-in")

    assert response.status_code == 200
    assert fake.check_in_calls == [(OWNER.user_id, 15)]


async def test_customer_cannot_use_owner_or_admin_api():
    fake = FakeReservationService()

    async with make_client(fake, user=ME) as client:
        owner_cancel = await client.post(
            "/api/v1/owner/reservations/15/cancel", json={"reason": "OTHER"}
        )
        check_in = await client.post("/api/v1/owner/reservations/15/check-in")
        admin_cancel = await client.post(
            "/api/v1/admin/reservations/15/cancel",
            json={"reason": "OTHER", "note": "메모"},
        )

    # 손님이 운영자·관리자 주소를 부르면 매니저까지 가지 않고 403이다.
    assert owner_cancel.status_code == 403
    assert check_in.status_code == 403
    assert admin_cancel.status_code == 403
    assert fake.cancel_calls == []
    assert fake.check_in_calls == []


async def test_owner_cannot_use_admin_api():
    fake = FakeReservationService()

    async with make_client(fake, user=OWNER) as client:
        response = await client.post(
            "/api/v1/admin/reservations/15/cancel",
            json={"reason": "OTHER", "note": "메모"},
        )

    assert response.status_code == 403
    assert fake.cancel_calls == []


async def test_admin_cancel_passes_reason_and_note():
    fake = FakeReservationService()

    async with make_client(fake, user=ADMIN) as client:
        response = await client.post(
            "/api/v1/admin/reservations/15/cancel",
            json={"reason": "SYSTEM_ERROR", "note": "중복 결제"},
        )

    assert response.status_code == 200
    assert fake.cancel_options == [
        (CancelledBy.ADMIN, CancelReason.SYSTEM_ERROR, "중복 결제")
    ]


async def test_cancel_request_rejects_unknown_reason_and_long_note():
    fake = FakeReservationService()

    async with make_client(fake, user=OWNER) as client:
        unknown = await client.post(
            "/api/v1/owner/reservations/15/cancel", json={"reason": "BORED"}
        )
        long_note = await client.post(
            "/api/v1/owner/reservations/15/cancel",
            json={"reason": "OTHER", "note": "가" * 101},
        )
        too_big = await client.post(f"/api/v1/owner/reservations/{10**19}/check-in")

    # 없는 이유, 100자 넘는 메모, BIGINT보다 큰 번호는 매니저까지 가지 않고 422다.
    assert unknown.status_code == 422
    assert long_note.status_code == 422
    assert too_big.status_code == 422
    assert fake.cancel_calls == []
    assert fake.check_in_calls == []


async def test_customer_cancel_still_sends_customer_request():
    fake = FakeReservationService()

    async with make_client(fake) as client:
        await client.post("/api/v1/reservations/15/cancel")

    # 손님 창구는 예전처럼 본문 없이 부르고, 누가=손님·이유=손님 요청으로 넘어간다.
    assert fake.cancel_options == [
        (CancelledBy.CUSTOMER, CancelReason.CUSTOMER_REQUEST, None)
    ]
