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
