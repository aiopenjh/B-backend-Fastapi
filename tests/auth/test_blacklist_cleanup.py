# [담당1 - 강성수] 만료된 블랙리스트 정리 테스트 (DB 없이 가짜 세션 사용)
from contextlib import asynccontextmanager
from datetime import UTC, datetime

from fastapi import FastAPI

from auth.infrastructure.models import TokenBlackListModel
from auth.infrastructure.repositories import purge_expired_tokens

NOW = datetime(2026, 11, 10, 3, 0, tzinfo=UTC)


class FakeSession:
    def __init__(self):
        self.statements = []
        self.committed = False

    async def execute(self, stmt):
        self.statements.append(stmt)

    async def commit(self):
        self.committed = True


def fake_session_factory(session: FakeSession):
    @asynccontextmanager
    async def factory():
        yield session

    return factory


async def test_purge_deletes_rows_expired_before_now_and_commits():
    session = FakeSession()

    await purge_expired_tokens(fake_session_factory(session), now=NOW)

    assert len(session.statements) == 1
    stmt = session.statements[0]
    assert stmt.is_delete
    assert stmt.table.name == TokenBlackListModel.__tablename__
    # 방향까지 확인: ">"로 뒤집히면 아직 유효한 블랙리스트가 지워져 로그아웃 토큰이 살아난다
    assert stmt.whereclause.compare(TokenBlackListModel.expired_at < NOW)
    assert session.committed is True


def test_user_id_foreign_key_has_index():
    assert TokenBlackListModel.__table__.c.user_id.index is True


async def test_lifespan_purges_expired_tokens_on_startup(monkeypatch):
    import main

    calls = []

    async def fake_purge(session_factory, now=None):
        calls.append(session_factory)

    class FakeConn:
        async def run_sync(self, fn):
            pass

    class FakeEngine:
        @asynccontextmanager
        async def begin(self):
            yield FakeConn()

        async def dispose(self):
            pass

    async def fake_seed(session):
        pass

    monkeypatch.setattr(main, "init_models", lambda: None)
    monkeypatch.setattr(main, "engine", FakeEngine())
    monkeypatch.setattr(main, "seed", fake_seed)
    monkeypatch.setattr(main, "AsyncSessionLocal", fake_session_factory(FakeSession()))
    monkeypatch.setattr(main, "purge_expired_tokens", fake_purge)

    async with main.lifespan(FastAPI()):
        # yield 전(시작 단계)에 정리됐는지 확인. 종료 단계로 옮겨지면 실패한다
        assert calls == [main.AsyncSessionLocal]
