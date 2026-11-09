# [담당3-영민] 테스트 픽스처 설정(testcode AI 작성)
import os
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
from httpx import ASGITransport, AsyncClient

from slot.domain.day_range import seoul_now
from slot.domain.repository import SlotRepository
from slot.domain.time_slot import TimeSlot

# 라우터 > container > common.database 가 POSTGRES_URL을 요구함
# 가짜 저장소를 쓰므로 실제 연결을 하지 않음(주소형식만 맞춤)
os.environ.setdefault("POSTGRES_URL", "postgresql+asyncpg://test:test@localhost:5432/test")


class InMemorySlotRepository(SlotRepository):
    def __init__(self, slots: list[TimeSlot], restaurant_ids: set[int]) -> None:
        self.slots = {s.id: s for s in slots}           # ▶ id → TimeSlot. 도메인 객체를 그대로 들고 있다 — ORM 이 없으니 _to_domain 도 없다
        self.restaurant_ids = restaurant_ids            # ▶ '존재하는 식당' 집합 — restaurant_exists 의 답
        self.locked: set[int] = set()                   # ▶ get_for_update 가 '잠갔다' 고 표시만 — 담당 4 가 호출 순서를 단언할 때 쓴다

    async def list_for_day(self, restaurant_id: int, start: datetime, end: datetime) -> list[TimeSlot]:
        return sorted(                                  # ▶ 실 구현과 같은 계약: 반개구간 · starts_at 오름차순 (② 인터페이스 독스트링)
            (s for s in self.slots.values() if s.restaurant_id == restaurant_id and start <= s.starts_at < end),
            key=lambda s: s.starts_at,
        )

    async def get_for_update(self, slot_id: int) -> TimeSlot | None:
        slot = self.slots.get(slot_id)
        if slot is not None:
            self.locked.add(slot_id)
        return slot

    async def save(self, slot: TimeSlot) -> None:
        if slot.id not in self.locked:
            raise LookupError(f"slot {slot.id} not locked")   # ▶ 실 구현의 '같은 세션이 아니면 LookupError' 와 같은 행동 — 가짜도 계약을 지켜야 가짜값이 있다
        self.slots[slot.id] = slot

    async def restaurant_exists(self, restaurant_id: int) -> bool:
        return restaurant_id in self.restaurant_ids


TOMORROW = seoul_now().replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)   # ▶ 내일 00:00+09:00 — '시작 전' 보장. 테스트와 픽스처가 같은 값을 쓴다


@pytest.fixture
def day() -> str:
    """조회 날짜 — 픽스처 슬롯과 같은 '내일'. 테스트 파일이 conftest 에서 상수를 import 하지 않게 픽스처로 넘긴다."""
    return TOMORROW.date().isoformat()


@pytest.fixture
def repo() -> InMemorySlotRepository:
    """식당 1 에 슬롯 2 (열린 · 거의 찬) — API_SPEC 예시 '슬롯 7 · 9' 의 값. 식당 99 는 없다."""
    slots = [
        # ▶ 이 슬롯만 UTC 로 보관한다 — 실 DB(timestamptz)가 돌려주는 모양. 라우터가 서울 시각으로 바꾸지 않으면 test_availability 의 "+09:00" 단언이 깨진다
        TimeSlot(id=7, restaurant_id=1,
                 starts_at=(TOMORROW + timedelta(hours=18)).astimezone(UTC),
                 ends_at=(TOMORROW + timedelta(hours=19)).astimezone(UTC),
                 capacity=10, reserved_guests=2, max_party_size=4),    # ▶ remaining 8
        TimeSlot(id=9, restaurant_id=1, starts_at=TOMORROW + timedelta(hours=19), ends_at=TOMORROW + timedelta(hours=20),
                 capacity=10, reserved_guests=8, max_party_size=4),    # ▶ remaining 2
    ]
    return InMemorySlotRepository(slots, restaurant_ids={1})


@pytest.fixture
async def client(repo: InMemorySlotRepository) -> AsyncIterator[AsyncClient]:
    """컨테이너의 팩토리를 가짜로 바꿔 끼운다 — 서비스·라우터·핸들러·봉투는 진짜 그대로."""
    # ▶ 앱 조립은 이 픽스처 안에서만 import — 파일 머리에 두면 같은 폴더의 ① 단위 테스트까지 앱 조립 상태에 묶인다
    # ▶ (11-06) main.app 이 아니라 '필요한 것만 붙인 앱' — slot 라우터의 main.py 등록 전에도 돌고, 남의 main.py 변경에 같이 깨지지 않는다
    # ▶ lifespan 없음 (create_all · 시드 없음). 메모리 레포라 상관없다
    # ▶ register_error_handlers: 422·404 봉투 — 빠지면 {"detail": ...}
    # ▶ register_middleware: request_id · 500 봉투 — 빠지면 request_id 가 None
    from fastapi import FastAPI

    from common.error_handlers import register_error_handlers
    from common.middleware import register_middleware
    from container import create_slot_repository
    from slot.presentation.router import router as slot_router

    app = FastAPI()
    register_middleware(app)
    register_error_handlers(app)
    app.include_router(slot_router, prefix="/api/v1")           # ▶ main.py 와 같은 접두어 — 테스트 URL 이 실서버와 같다

    app.dependency_overrides[create_slot_repository] = lambda: repo   # ▶ Depends(create_slot_repository) 를 받는 create_slot_service 까지 따라온다 (③ §1). get_session 은 호출조차 안 된다 → DB 불필요
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()                    # ▶ 다음 테스트에 새지 않게
