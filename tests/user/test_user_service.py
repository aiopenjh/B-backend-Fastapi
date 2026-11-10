# [담당1 - 강성수] UserService 테스트 (메모리 레포지토리 사용)
import asyncio
import threading
import uuid
from datetime import UTC, datetime

import pytest

from common.errors import InvalidInputError
from common.unit_of_work import ConflictError, UnitOfWork
from user.application.service import UserService
from user.domain.exceptions import DuplicatedUserError, UserNotFoundError
from user.domain.hasher import PasswordHasher
from user.domain.repository import UserRepository
from user.domain.user import User
from user.domain.value_object import Email

VALID_PASSWORD = "abcd1234!"


class InMemoryUserRepository(UserRepository):
    """DB 대신 이메일을 키로 사용자를 보관하는 가짜 레포지토리"""

    def __init__(self) -> None:
        self.users: dict[Email, User] = {}

    async def find_by_id(self, user_id: uuid.UUID) -> User | None:
        return next((u for u in self.users.values() if u.id == user_id), None)

    async def find_by_email(self, email: Email) -> User | None:
        return self.users.get(email)

    async def save(self, user: User) -> User:
        if user.id is None:
            user.id = uuid.uuid4()
        self.users[user.email] = user
        return user


class FakeUnitOfWork(UnitOfWork):
    """commit 호출 횟수를 세는 가짜 UoW. conflict=True면 commit에서 충돌을 낸다"""

    def __init__(self, conflict: bool = False) -> None:
        self.commits = 0
        self.conflict = conflict

    async def commit(self) -> None:
        if self.conflict:
            raise ConflictError()
        self.commits += 1


@pytest.fixture
def repo() -> InMemoryUserRepository:
    return InMemoryUserRepository()


@pytest.fixture
def uow() -> FakeUnitOfWork:
    return FakeUnitOfWork()


@pytest.fixture
def service(repo, uow, hasher) -> UserService:
    return UserService(repo=repo, uow=uow, hasher=hasher)


class LoopProbeHasher(PasswordHasher):
    """hash가 도는 동안 이벤트 루프가 다른 코루틴을 실행할 수 있는지 잰다.

    hash가 루프 스레드에서 돌면 ticker가 실행되지 못해 progressed를 기다리다 시간이 끝난다.
    """

    def __init__(self, events: list[str] | None = None) -> None:
        self.started = threading.Event()
        self.progressed = threading.Event()
        self.loop_blocked: bool | None = None
        self.events = events if events is not None else []

    def hash(self, raw_password: str) -> str:
        self.events.append("hash")
        self.started.set()
        self.loop_blocked = not self.progressed.wait(timeout=1.0)
        return f"hashed:{raw_password}"

    def verify(self, raw_password: str, hashed_password: str) -> bool:
        return self.hash(raw_password) == hashed_password


async def tick_until_started(hasher: LoopProbeHasher) -> None:
    while not hasher.started.is_set():
        await asyncio.sleep(0.001)
    hasher.progressed.set()


class EventRecordingUnitOfWork(FakeUnitOfWork):
    def __init__(self, events: list[str]) -> None:
        super().__init__()
        self.events = events

    async def release(self) -> None:
        self.events.append("release")

    async def commit(self) -> None:
        self.events.append("commit")
        await super().commit()


async def test_sign_up_keeps_event_loop_running_while_hashing(repo, uow):
    probe = LoopProbeHasher()
    service = UserService(repo=repo, uow=uow, hasher=probe)

    user, _ = await asyncio.gather(
        service.sign_up(
            "alice@example.com", VALID_PASSWORD, "김철수", "010-1234-5678"
        ),
        tick_until_started(probe),
    )

    assert user.password_hash == f"hashed:{VALID_PASSWORD}"
    assert probe.loop_blocked is False


class ReadRecordingUserRepository(InMemoryUserRepository):
    def __init__(self, events: list[str]) -> None:
        super().__init__()
        self.events = events

    async def find_by_email(self, email: Email) -> User | None:
        self.events.append("read")
        return await super().find_by_email(email)


def make_recording_service(events: list[str]) -> UserService:
    probe = LoopProbeHasher(events)
    probe.progressed.set()  # 루프 측정은 위 테스트가 함. 여기선 순서만 본다
    return UserService(
        repo=ReadRecordingUserRepository(events),
        uow=EventRecordingUnitOfWork(events),
        hasher=probe,
    )


async def test_sign_up_releases_read_transaction_between_read_and_hash():
    events: list[str] = []
    service = make_recording_service(events)

    await service.sign_up(
        "alice@example.com", VALID_PASSWORD, "김철수", "010-1234-5678"
    )

    # 읽은 뒤에 끝내야 해시 중 연결을 붙잡지 않는다. 읽기 전에 끝내면 의미가 없다
    assert events == ["read", "release", "hash", "commit"]


async def test_sign_up_rejected_inside_hash_thread_saves_and_commits_nothing(
    repo, uow
):
    # User.create의 비밀번호 검증은 스레드 안에서 실패한다. 예외가 호출한 쪽까지 와야 한다
    service = UserService(repo=repo, uow=uow, hasher=LoopProbeHasher())

    with pytest.raises(InvalidInputError) as exc:
        await service.sign_up(
            "alice@example.com", "short", "김철수", "010-1234-5678"
        )

    assert "password" in exc.value.errors
    assert repo.users == {}
    assert uow.commits == 0


async def test_sign_up_duplicate_email_does_not_hash():
    events: list[str] = []
    service = make_recording_service(events)
    await service.sign_up(
        "alice@example.com", VALID_PASSWORD, "김철수", "010-1234-5678"
    )
    events.clear()

    with pytest.raises(DuplicatedUserError):
        await service.sign_up(
            "alice@example.com", VALID_PASSWORD, "고길동", "010-1234-5678"
        )

    assert "hash" not in events


async def test_sign_up_saves_user_with_normalized_email(service, repo):
    user = await service.sign_up(
        "  Alice@Example.COM ", VALID_PASSWORD, "김철수", "010-1234-5678"
    )

    assert user.email == Email("alice@example.com")
    assert user.id is not None
    assert await repo.find_by_email(Email("alice@example.com")) is user


async def test_sign_up_rejects_email_already_registered_ignoring_case(service, repo):
    await service.sign_up("alice@example.com", VALID_PASSWORD, "김철수", "010-1234-5678")

    with pytest.raises(DuplicatedUserError):
        await service.sign_up(
            "ALICE@example.com", VALID_PASSWORD, "김영희", "010-9876-5432"
        )

    assert len(repo.users) == 1


async def test_sign_up_with_invalid_email_saves_nothing(service, repo):
    with pytest.raises(InvalidInputError):
        await service.sign_up("not-an-email", VALID_PASSWORD, "김철수", "010-1234-5678")

    assert repo.users == {}


async def test_sign_up_commits_once(service, uow):
    await service.sign_up("alice@example.com", VALID_PASSWORD, "고길동", "010-1234-5678")

    assert uow.commits == 1


async def test_rejected_sign_up_does_not_commit(service, uow):
    with pytest.raises(InvalidInputError):
        await service.sign_up("not-an-email", VALID_PASSWORD, "고길동", "010-1234-5678")

    assert uow.commits == 0


async def test_conflict_at_commit_becomes_duplicated_user(repo, hasher):
    service = UserService(repo=repo, uow=FakeUnitOfWork(conflict=True), hasher=hasher)

    with pytest.raises(DuplicatedUserError):
        await service.sign_up("test@test.org", VALID_PASSWORD, "고길동", "010-1234-5678")


async def test_get_user_success_returns_saved_user(service, repo):
    saved = await service.sign_up(
        "alice@example.com", VALID_PASSWORD, "고길동", "010-1234-5678"
    )

    assert await service.get_user(saved.id) is saved


async def test_get_user_fail_unknown_id(service):
    with pytest.raises(UserNotFoundError):
        await service.get_user(uuid.uuid4())


async def test_get_user_fail_deleted_user(service):
    saved = await service.sign_up(
        "alice@example.com", VALID_PASSWORD, "고길동", "010-1234-5678"
    )

    saved.deleted_at = datetime.now(UTC)

    with pytest.raises(UserNotFoundError):
        await service.get_user(saved.id)
