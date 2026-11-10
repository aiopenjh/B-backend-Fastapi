# [담당1 - 강성수] 만료된 블랙리스트 정리 테스트 (DB 없이 가짜 세션 사용)
from contextlib import asynccontextmanager
from datetime import UTC, datetime

from fastapi import FastAPI
from sqlalchemy.dialects import postgresql

from auth.domain.token_entities import BLACKLIST_PURGE_GRACE
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
    compiled = stmt.compile(dialect=postgresql.dialect())
    sql = " ".join(str(compiled).split())
    # 방향까지 확인: ">"로 뒤집히면 아직 유효한 블랙리스트가 지워져 로그아웃 토큰이 살아난다
    assert "token_blacklist.expired_at <" in sql
    # 서버 간 시계 차이를 생각해 여유 시간만큼 이전에 만료된 행만 지운다
    assert list(compiled.params.values()) == [NOW - BLACKLIST_PURGE_GRACE]
    # 다른 트랜잭션이 잠근 행은 기다리지 않고 건너뛴다 (로그아웃 응답이 막히지 않게)
    assert "FOR UPDATE SKIP LOCKED" in sql
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
