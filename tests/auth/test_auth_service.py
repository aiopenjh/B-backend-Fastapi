# [담당1 - 강성수]

import asyncio
import threading
import uuid
from datetime import datetime, UTC

import pytest

from auth.application.service import AuthService
from auth.domain.exceptions import InvalidCredentialsError
from auth.domain.repository import TokenBlackListRepository
from auth.domain.token_entities import BlackListToken
from auth.domain.value_object import AuthRole
from auth.infrastructure.security import JwtTokenProvider

from common.errors import UnauthorizedError
from common.unit_of_work import ConflictError, UnitOfWork

from user.domain.hasher import PasswordHasher
from user.domain.repository import UserRepository
from user.domain.user import User, Role
from user.domain.value_object import Email

SECRET = "k" * 64
PASSWORD = "abcd1234!"


class FakePasswordHasher(PasswordHasher):
    """bcrypt 대신 결과를 예측할 수 있는 가짜 해시"""

    def hash(self, raw_password: str) -> str:
        return f"hashed:{raw_password}"

    def verify(self, raw_password: str, hashed_password: str) -> bool:
        return self.hash(raw_password) == hashed_password


class InMemoryUserRepository(UserRepository):
    def __init__(self) -> None:
        self.users: dict[uuid.UUID, User] = {}

    async def find_by_id(self, user_id: uuid.UUID) -> User | None:
        return self.users.get(user_id)

    async def find_by_email(self, email: Email) -> User | None:
        return next((u for u in self.users.values() if u.email == email), None)

    async def save(self, user: User) -> User:
        self.users[user.id] = user
        return user


class InMemoryBlackListRepository(TokenBlackListRepository):
    """add는 대기열에만 넣고, FakeUnitOfWork.commit이 불려야 확정된다."""

    def __init__(self) -> None:
        self.jtis: set[str] = set()
        self.saved: list[BlackListToken] = []
        self.pending: list[BlackListToken] = []

    async def add(self, token: BlackListToken) -> None:
        self.pending.append(token)

    async def is_blacklisted(self, jti: str) -> bool:
        return jti in self.jtis

    async def cleanup_expired(self, current_time: datetime) -> None:
        pass


class FakeUnitOfWork(UnitOfWork):
    """commit 호출 횟수를 세는 가짜 UoW. conflict=True면 commit에서 충돌을 낸다"""

    def __init__(
        self, blacklist: InMemoryBlackListRepository, conflict: bool = False
    ) -> None:
        self.blacklist = blacklist
        self.commits = 0
        self.conflict = conflict

    async def commit(self) -> None:
        if self.conflict:
            self.blacklist.pending.clear()
            raise ConflictError()

        for token in self.blacklist.pending:
            self.blacklist.jtis.add(token.jti)
            self.blacklist.saved.append(token)

        self.blacklist.pending.clear()
        self.commits += 1


@pytest.fixture
def hasher() -> FakePasswordHasher:
    return FakePasswordHasher()


@pytest.fixture
def user_repo() -> InMemoryUserRepository:
    return InMemoryUserRepository()


@pytest.fixture
def blacklist() -> InMemoryBlackListRepository:
    return InMemoryBlackListRepository()


@pytest.fixture
def uow(blacklist: InMemoryBlackListRepository) -> FakeUnitOfWork:
    return FakeUnitOfWork(blacklist=blacklist)


@pytest.fixture
def service(user_repo, hasher, blacklist, uow) -> AuthService:
    return AuthService(
        user_repo=user_repo,
        hasher=hasher,
        token_provider=JwtTokenProvider(secret_key=SECRET),
        blacklist_repo=blacklist,
        uow=uow,
    )


@pytest.fixture
async def user(user_repo, hasher) -> User:
    created = User.create(
        email=Email("owner@example.com"),
        raw_password=PASSWORD,
        name="고길동",
        phone="010-1234-5678",
        hasher=hasher,
        role=Role.OWNER,
    )

    return await user_repo.save(created)


class LoopProbeHasher(FakePasswordHasher):
    """verify가 도는 동안 이벤트 루프가 다른 코루틴을 실행할 수 있는지 잰다.

    verify가 루프 스레드에서 돌면 ticker가 실행되지 못해 progressed를 기다리다 시간이 끝난다.
    """

    def __init__(self, events: list[str] | None = None) -> None:
        self.started = threading.Event()
        self.progressed = threading.Event()
        self.loop_blocked: bool | None = None
        self.events = events if events is not None else []

    def verify(self, raw_password: str, hashed_password: str) -> bool:
        self.events.append("verify")
        self.started.set()
        self.loop_blocked = not self.progressed.wait(timeout=1.0)
        return super().verify(raw_password, hashed_password)


async def tick_until_started(hasher: LoopProbeHasher) -> None:
    while not hasher.started.is_set():
        await asyncio.sleep(0.001)
    hasher.progressed.set()


class ReleaseRecordingUnitOfWork(FakeUnitOfWork):
    def __init__(self, blacklist, events: list[str]) -> None:
        super().__init__(blacklist=blacklist)
        self.events = events

    async def release(self) -> None:
        self.events.append("release")


def make_service(user_repo, hasher, blacklist, uow) -> AuthService:
    return AuthService(
        user_repo=user_repo,
        hasher=hasher,
        token_provider=JwtTokenProvider(secret_key=SECRET),
        blacklist_repo=blacklist,
        uow=uow,
    )


async def test_login_keeps_event_loop_running_while_verifying(
    user_repo, blacklist, uow, user
):
    probe = LoopProbeHasher()
    service = make_service(user_repo, probe, blacklist, uow)

    issued, _ = await asyncio.gather(
        service.login("owner@example.com", PASSWORD), tick_until_started(probe)
    )

    assert issued.access_token
    assert probe.loop_blocked is False


class ReadRecordingUserRepository(InMemoryUserRepository):
    def __init__(self, events: list[str]) -> None:
        super().__init__()
        self.events = events

    async def find_by_email(self, email: Email) -> User | None:
        self.events.append("read")
        return await super().find_by_email(email)


async def test_login_releases_read_transaction_between_read_and_verify(blacklist, user):
    events: list[str] = []
    repo = ReadRecordingUserRepository(events)
    repo.users[user.id] = user
    probe = LoopProbeHasher(events)
    probe.progressed.set()  # 루프 측정은 위 테스트가 함. 여기선 순서만 본다
    uow = ReleaseRecordingUnitOfWork(blacklist, events)
    service = make_service(repo, probe, blacklist, uow)

    await service.login("owner@example.com", PASSWORD)

    # 읽은 뒤에 끝내야 해시 중 연결을 붙잡지 않는다. 읽기 전에 끝내면 의미가 없다
    assert events == ["read", "release", "verify"]


async def test_login_success_returns_token_for_users(service, user):
    issued = await service.login("owner@example.com", PASSWORD)

    authenticated = await service.authenticate(issued.access_token)

    assert authenticated.user_id == user.id
    assert issued.expires_in > 0


async def test_login_success_with_uppercase_email(service, user):
    issued = await service.login("  OWNER@Example.com", PASSWORD)

    assert (await service.authenticate(issued.access_token)).user_id == user.id


async def test_login_fail_wrong_password(service, user):
    with pytest.raises(InvalidCredentialsError):
        await service.login("owner@example.com", "wrong1234!")


async def test_login_fail_unknown_email(service, user):
    with pytest.raises(InvalidCredentialsError):
        await service.login("nobody@example.com", PASSWORD)


async def test_login_fail_malformed_email(service, user):
    with pytest.raises(InvalidCredentialsError):
        await service.login("not-an-email", PASSWORD)


async def test_login_fail_deleted_user(service, user):
    user.deleted_at = datetime.now(UTC)

    with pytest.raises(InvalidCredentialsError):
        await service.login("owner@example.com", PASSWORD)


async def test_authenticate_success_returns_current_role(service, user):
    issued = await service.login("owner@example.com", PASSWORD)

    authenticated = await service.authenticate(issued.access_token)

    assert authenticated.user_id == user.id
    assert authenticated.role is AuthRole.OWNER


async def test_authenticate_fail_invalid_token(service, user):
    with pytest.raises(UnauthorizedError):
        await service.authenticate("not-a-jwt")


async def test_authenticate_fail_blacklisted_token(service, user, blacklist):
    issued = await service.login("owner@example.com", PASSWORD)

    payload = JwtTokenProvider(secret_key=SECRET).decode_token(issued.access_token)
    blacklist.jtis.add(payload.jti)

    with pytest.raises(UnauthorizedError):
        await service.authenticate(issued.access_token)


async def test_authenticate_fail_deleted_user(service, user):
    issued = await service.login("owner@example.com", PASSWORD)

    user.deleted_at = datetime.now(UTC)

    with pytest.raises(UnauthorizedError):
        await service.authenticate(issued.access_token)


async def test_authenticate_fail_unknown_user(service, user, user_repo):
    issued = await service.login("owner@example.com", PASSWORD)

    user_repo.users.clear()

    with pytest.raises(UnauthorizedError):
        await service.authenticate(issued.access_token)


async def test_logout_success_blocks_the_token(service, user, blacklist, uow):
    issued = await service.login("owner@example.com", PASSWORD)

    await service.logout(issued.access_token)

    with pytest.raises(UnauthorizedError):
        await service.authenticate(issued.access_token)

    assert uow.commits == 1
    assert blacklist.saved[0].user_id == user.id


async def test_logout_success_keeps_other_tokens_valid(service, user):
    first = await service.login("owner@example.com", PASSWORD)
    second = await service.login("owner@example.com", PASSWORD)

    await service.logout(first.access_token)

    assert (await service.authenticate(second.access_token)).user_id == user.id


async def test_login_again_after_logout_issues_working_token(service, user):
    first = await service.login("owner@example.com", PASSWORD)
    await service.logout(first.access_token)

    second = await service.login("owner@example.com", PASSWORD)

    assert (await service.authenticate(second.access_token)).user_id == user.id
    with pytest.raises(UnauthorizedError):
        await service.authenticate(first.access_token)


async def test_logout_fail_already_logged_out(service, user, uow):
    issued = await service.login("owner@example.com", PASSWORD)

    await service.logout(issued.access_token)

    with pytest.raises(UnauthorizedError):
        await service.logout(issued.access_token)
    assert uow.commits == 1


async def test_logout_fail_invalid_token(service, blacklist, uow):
    with pytest.raises(UnauthorizedError):
        await service.logout("not-a-jwt")

    assert blacklist.saved == []
    assert uow.commits == 0


async def test_logout_conflict_at_commit_becomes_unauthorized(
    user_repo, hasher, blacklist, user
):
    service = AuthService(
        user_repo=user_repo,
        hasher=hasher,
        token_provider=JwtTokenProvider(secret_key=SECRET),
        blacklist_repo=blacklist,
        uow=FakeUnitOfWork(blacklist=blacklist, conflict=True),
    )

    issued = await service.login("owner@example.com", PASSWORD)

    with pytest.raises(UnauthorizedError):
        await service.logout(issued.access_token)
