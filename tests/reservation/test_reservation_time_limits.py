# [담당 4] 예약 트랜잭션 시간 제한 테스트 : 값 검사(0은 무제한이라 금지, 락 대기 < 쿼리 제한), 환경변수 읽기
from datetime import timedelta

import pytest

import container
from reservation.infrastructure.time_limits import DEFAULT_TIME_LIMITS, TimeLimits

SECOND = timedelta(seconds=1)


# 기본값: 락 대기 3초 < 쿼리 5초, 멈춘 트랜잭션 10초
def test_default_time_limits():
    assert DEFAULT_TIME_LIMITS == TimeLimits(
        lock=3 * SECOND, statement=5 * SECOND, idle_in_transaction=10 * SECOND
    )


# PostgreSQL 설정값은 밀리초 글자로 만든다 (SET은 값 자리에 변수를 못 써서, 정수로만 만들어 넣는다)
def test_time_limits_as_settings_in_milliseconds():
    limits = TimeLimits(
        lock=timedelta(milliseconds=500),
        statement=SECOND,
        idle_in_transaction=timedelta(seconds=1, milliseconds=250),
    )

    assert limits.as_settings() == {
        "lock_timeout": "500ms",
        "statement_timeout": "1000ms",
        "idle_in_transaction_session_timeout": "1250ms",
    }


# 0은 PostgreSQL에서 "무제한"이라 안전장치가 꺼진다. 0, 음수, 1밀리초보다 작은 값은 막는다
@pytest.mark.parametrize(
    "field", ["lock", "statement", "idle_in_transaction"], ids=lambda f: f
)
@pytest.mark.parametrize(
    "bad",
    [timedelta(0), -SECOND, timedelta(microseconds=500)],
    ids=["zero", "negative", "under_1ms"],
)
def test_time_limits_reject_zero_or_negative(field, bad):
    values = {
        "lock": SECOND,
        "statement": 2 * SECOND,
        "idle_in_transaction": 2 * SECOND,
    }
    values[field] = bad

    # 0·음수 검사가 순서 검사보다 먼저라, 에러 문구에 잘못된 칸 이름이 나온다
    with pytest.raises(ValueError, match=field):
        TimeLimits(**values)


# 쿼리 제한은 락 기다림도 포함해서 잰다. 락 대기가 같거나 길면 기다림이 409가 아니라 503으로 끝나서 막는다
@pytest.mark.parametrize("lock_seconds", [5, 6])
def test_time_limits_lock_must_be_shorter_than_statement(lock_seconds):
    with pytest.raises(ValueError):
        TimeLimits(
            lock=lock_seconds * SECOND,
            statement=5 * SECOND,
            idle_in_transaction=10 * SECOND,
        )


# 환경변수가 없으면 기본값을 쓴다
def test_reservation_time_limits_default(monkeypatch):
    for name in (
        "RESERVATION_LOCK_TIMEOUT_SECONDS",
        "RESERVATION_STATEMENT_TIMEOUT_SECONDS",
        "RESERVATION_IDLE_IN_TRANSACTION_TIMEOUT_SECONDS",
    ):
        monkeypatch.delenv(name, raising=False)

    assert container.reservation_time_limits() == DEFAULT_TIME_LIMITS


# 환경변수로 바꿀 수 있다
def test_reservation_time_limits_from_env(monkeypatch):
    monkeypatch.setenv("RESERVATION_LOCK_TIMEOUT_SECONDS", "2")
    monkeypatch.setenv("RESERVATION_STATEMENT_TIMEOUT_SECONDS", "4")
    monkeypatch.setenv("RESERVATION_IDLE_IN_TRANSACTION_TIMEOUT_SECONDS", "8")

    assert container.reservation_time_limits() == TimeLimits(
        lock=2 * SECOND, statement=4 * SECOND, idle_in_transaction=8 * SECOND
    )


# 0(무제한)이나 순서가 틀린 값이 들어오면 앱이 죽지 않고 경고 후 기본값으로 돌아간다 (안전장치가 꺼지지 않게)
@pytest.mark.parametrize(
    ("lock", "statement", "idle"),
    [
        ("0", "5", "10"),
        ("3", "0", "10"),
        ("3", "5", "0"),
        ("5", "5", "10"),
        ("9", "5", "10"),
    ],
)
def test_reservation_time_limits_bad_env_falls_back(monkeypatch, lock, statement, idle):
    monkeypatch.setenv("RESERVATION_LOCK_TIMEOUT_SECONDS", lock)
    monkeypatch.setenv("RESERVATION_STATEMENT_TIMEOUT_SECONDS", statement)
    monkeypatch.setenv("RESERVATION_IDLE_IN_TRANSACTION_TIMEOUT_SECONDS", idle)

    assert container.reservation_time_limits() == DEFAULT_TIME_LIMITS
