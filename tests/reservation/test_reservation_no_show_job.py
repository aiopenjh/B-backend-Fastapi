# [담당 4] 자동 노쇼 반복 테스트 : 반복이 계속 돌고, 실패해도 멈추지 않고, 끌 때는 멈추는지
import asyncio

import pytest

import container


async def test_loop_keeps_running_after_error_and_stops_on_cancel(monkeypatch):
    calls: list[int] = []

    async def fake_expire_once(session_factory, now) -> int:
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("DB가 잠깐 끊김")  # 첫 번째는 실패하는 흉내
        return 0

    monkeypatch.setattr(container, "expire_no_shows_once", fake_expire_once)

    task = asyncio.create_task(container.run_no_show_loop(None, 0.01))
    await asyncio.sleep(0.1)

    # 첫 번째가 실패해도 로그만 남기고 다음 반복을 계속 돈다.
    assert len(calls) >= 2

    # 앱을 끌 때처럼 멈추면 반복이 끝난다.
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    stopped_at = len(calls)
    await asyncio.sleep(0.05)
    assert len(calls) == stopped_at


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (None, 900),
        ("", 900),
        ("   ", 900),
        ("600", 600),
        ("0", 0),
        ("abc", 900),
        ("-5", 900),
    ],
)
def test_env_seconds_falls_back_to_default(monkeypatch, raw, expected):
    # 환경변수가 비었거나 숫자가 아니거나 음수면 앱이 죽지 않고 기본값을 쓴다
    if raw is None:
        monkeypatch.delenv("NO_SHOW_TEST_SECONDS", raising=False)
    else:
        monkeypatch.setenv("NO_SHOW_TEST_SECONDS", raw)

    assert container.env_seconds("NO_SHOW_TEST_SECONDS", 900) == expected
