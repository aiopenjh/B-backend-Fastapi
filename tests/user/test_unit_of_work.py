# [담당1 - 강성수] UnitOfWork.release 테스트 (DB 없이 가짜 세션 사용)
from common.unit_of_work import UnitOfWork
from user.infrastructure.unit_of_work import SQLAlchemyUnitOfWork


class FakeSession:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def rollback(self) -> None:
        self.calls.append("rollback")

    async def commit(self) -> None:
        self.calls.append("commit")


async def test_release_ends_transaction_without_committing():
    session = FakeSession()

    await SQLAlchemyUnitOfWork(session=session).release()

    # 읽기만 한 트랜잭션을 끝내 연결을 풀에 돌려준다. 확정(commit)은 하지 않는다
    assert session.calls == ["rollback"]


async def test_release_defaults_to_noop_for_other_implementations():
    class CommitOnlyUnitOfWork(UnitOfWork):
        async def commit(self) -> None:
            pass

    await CommitOnlyUnitOfWork().release()
