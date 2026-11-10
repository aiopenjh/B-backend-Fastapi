# [담당3-영민] tests/slot/test_availability.py — 날짜는 conftest 의 day 픽스처 (testcode AI 작성)
from httpx import AsyncClient


async def test_open_slot_true_nearly_full_false(client: AsyncClient, day: str):
    """G5 성공 요청: 인원 3 → 열린 슬롯 true, 거의 찬 슬롯(remaining 2) false. 같은 200 안에 둘 다 (API_SPEC §1)."""
    r = await client.get("/api/v1/restaurants/1/availability", params={"date": day, "party_size": 3})
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True and body["code"] == "OK" and body["errors"] is None   # ▶ 성공 봉투 (v2)
    assert body["request_id"] == r.headers["X-Request-ID"]                             # ▶ 봉투와 헤더가 같은 id — 미들웨어 ↔ ContextVar 연결 확인
    data = body["data"]
    assert data["restaurant_id"] == 1 and data["date"] == day
    by_remaining = {s["remaining"]: s["available"] for s in data["slots"]}             # ▶ id 가 아니라 값으로 — 실 DB 에서는 id 가 자동 증가라 하드코딩하지 않는 습관
    assert by_remaining == {8: True, 2: False}
    assert data["slots"][0]["starts_at"].endswith("T18:00:00+09:00")                   # ▶ 저장은 UTC(conftest), 응답은 서울 18시 — 라우터의 astimezone(SEOUL) 확인 · 정렬 첫 줄
    assert "capacity" not in data["slots"][0]                                          # ▶ 내부 재고 숫자는 내보내지 않는다 (③ §3)


async def test_party_size_zero_is_422_envelope(client: AsyncClient, day: str):
    """G5 실패 요청: 형식 오류는 서비스에 닿기 전에 422 — 실패 봉투."""
    r = await client.get("/api/v1/restaurants/1/availability", params={"date": day, "party_size": 0})
    assert r.status_code == 422
    body = r.json()
    assert body["success"] is False and body["code"] == "VALIDATION_ERROR" and body["data"] is None
    assert "party_size" in body["errors"] and isinstance(body["errors"]["party_size"], list)   # ▶ {필드: [메시지]} — 핸들러의 loc 변환 (④ §4)
    assert body["request_id"] == r.headers["X-Request-ID"]


async def test_unknown_restaurant_is_404_envelope(client: AsyncClient, day: str):
    r = await client.get("/api/v1/restaurants/99/availability", params={"date": day, "party_size": 2})
    assert r.status_code == 404
    body = r.json()
    assert body["code"] == "RESTAURANT_NOT_FOUND" and body["message"] == "식당을 찾을 수 없습니다."
    assert body["errors"] == {"restaurant_id": ["id 99 인 식당이 없습니다."]}            # ▶ AppError 의 errors 가 봉투로 그대로 (③ §2)


async def test_over_max_party_is_available_false_not_409(client: AsyncClient, day: str):
    """조회는 409 를 내지 않는다 — 규칙 위반은 available false 로 (API_SPEC §1)."""
    r = await client.get("/api/v1/restaurants/1/availability", params={"date": day, "party_size": 5})   # ▶ 5 > max 4
    assert r.status_code == 200
    assert all(s["available"] is False for s in r.json()["data"]["slots"])


async def test_missing_date_is_422(client: AsyncClient):
    """⓪ A3 — date 는 필수."""
    r = await client.get("/api/v1/restaurants/1/availability", params={"party_size": 2})
    assert r.status_code == 422 and "date" in r.json()["errors"]
