# [담당3-영민] TimeSlot 도메인 테스트
from datetime import datetime, timedelta

import pytest

from slot.domain.day_range import SEOUL
from slot.domain.exceptions import (
    PartySizeExceeded,
    SlotAlreadyStarted,
    SlotErrorCode,
    SlotRuleViolation,
    SlotSoldOut,
)
from slot.domain.time_slot import TimeSlot

NOW = datetime(2026, 11, 4, 12, 0, tzinfo=SEOUL)

def make(**over) -> TimeSlot:
    """기본값: 내일 18~19시, 정원 10, 예약2, 1회 최대 4 (API_SPEC 예시 '슬롯 7')"""
    base = {"id": 7, "restaurant_id": 1, "starts_at": NOW + timedelta(days=1, hours=6),
        "ends_at": NOW + timedelta(days=1, hours=7),
        "capacity": 10, 
        "reserved_guests": 2, 
        "max_party_size": 4}
    return TimeSlot(**{**base, **over})



def test_can_accept_open_slot():
    assert make().can_accept(3, NOW) is True


def test_started_slot_is_rejected_first():
    slot = make(starts_at=NOW - timedelta(hours=1), ends_at=NOW + timedelta(hours=1), reserved_guests=10)
    assert slot.can_accept(3, NOW) is False
    with pytest.raises(SlotAlreadyStarted):
        slot.reserve(3, NOW)


def test_party_size_over_max():
    with pytest.raises(PartySizeExceeded):
        make().reserve(5, NOW)                                 # ▶ 5 > max 4 (remaining 8 이라도)


def test_sold_out_carries_code_status_and_errors():
    slot = make(reserved_guests=8)                             # ▶ API_SPEC '슬롯 9': remaining 2
    assert slot.can_accept(3, NOW) is False
    with pytest.raises(SlotSoldOut) as e:
        slot.reserve(3, NOW)
    err = e.value
    assert err.error_code is SlotErrorCode.SLOT_SOLD_OUT       # ▶ 예외가 enum 멤버를 가리킨다
    assert err.status_code == 409 and err.error_code.code == "SLOT_SOLD_OUT"   # ▶ .code 는 ErrorCode 믹스인의 name
    assert err.errors == {"party_size": ["남은 자리(2명)보다 많습니다. 요청: 3명"]}   # ▶ API_SPEC §4 실패 예시 그대로
    assert isinstance(err, SlotRuleViolation)                  # ▶ 담당 4 가 '규칙 위반이면 뭐든' 으로 잡을 수 있다


def test_remaining_and_has_started():
    slot = make()
    assert slot.remaining == 8                                 # ▶ capacity 10 - reserved 2
    assert slot.has_started(NOW) is False                      # ▶ 내일 18시 — 아직 전
    assert slot.has_started(slot.starts_at) is True            # ▶ 시작 시각 '그 순간' 부터 시작으로 본다 (now >= starts_at)


def test_reserve_then_release_roundtrip():
    slot = make()
    slot.reserve(3, NOW)
    assert slot.reserved_guests == 5                           # ▶ 2 + 3
    slot.release(3)
    assert slot.reserved_guests == 2                           # ▶ 한 번만 복구 — 두 번째 release 는 Reservation 쪽이 막는다


def test_release_below_zero_is_error():
    with pytest.raises(ValueError):
        make(reserved_guests=0).release(1)


def test_constructor_rejects_naive_datetime():
    with pytest.raises(ValueError):
        make(starts_at=datetime(2026, 11, 5, 18), ends_at=datetime(2026, 11, 5, 19))


def test_started_and_party_size_errors_are_field_to_list():
    """봉투 errors 는 {필드: [문장]} — 값이 list[str] 이 아니면 담당 2 핸들러에서 500 이 된다"""
    started = make(starts_at=NOW - timedelta(hours=1), ends_at=NOW + timedelta(hours=1))
    with pytest.raises(SlotAlreadyStarted) as e1:
        started.reserve(1, NOW)
    with pytest.raises(PartySizeExceeded) as e2:
        make().reserve(5, NOW)
    for err in (e1.value, e2.value):
        assert err.message == err.error_code.message                      # ▶ message 를 따로 넘기지 않는다 — enum 문구 하나가 진실
        assert all(isinstance(v, list) and all(isinstance(x, str) for x in v) for v in err.errors.values())
    assert "slot_id" in e1.value.errors and "party_size" in e2.value.errors
