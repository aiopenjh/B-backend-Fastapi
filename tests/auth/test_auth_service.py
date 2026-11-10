# [담당1 - 강성수]

import asyncio
import threading
import time
import uuid
from datetime import datetime, UTC

import bcrypt
import pytest

from auth.application.service import DUMMY_PASSWORD, AuthService
from auth.domain.exceptions import (
    InvalidCredentialsError,
    TooManyLoginAttemptsError,
)
from auth.domain.repository import TokenBlackListRepository
from auth.domain.token_entities import BlackListToken
from auth.domain.value_object import AuthRole
from auth.infrastructure.login_limiter import InMemoryLoginAttemptLimiter
from auth.infrastructure.security import JwtTokenProvider

from common.errors import UnauthorizedError
from common.unit_of_work import ConflictError, UnitOfWork

from user.domain.hasher import PasswordHasher
from user.domain.repository import UserRepository
from user.domain.user import User, Role
from user.domain.value_object import Email
from user.infrastructure.security import BcryptPasswordHasher

SECRET = "k" * 64
PASSWORD = "abcd1234!"
CLIENT_IP = "10.0.0.1"


class FakePasswordHasher(PasswordHasher):
    """bcrypt 대신 결과를 예측할 수 있는 가짜 해시"""

    def hash(self, raw_password: str) -> str:
        return f"hashed:{raw_password}"

    def verify(self, raw_password: str, hashed_password: str) -> bool:
        return self.hash(raw_password) == hashed_password


# 실제 앱은 container가 시작할 때 한 번 만든다
DUMMY_HASH = FakePasswordHasher().hash(DUMMY_PASSWORD)


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
def login_limiter() -> InMemoryLoginAttemptLimiter:
    return InMemoryLoginAttemptLimiter()


@pytest.fixture
def service(user_repo, hasher, blacklist, uow, login_limiter) -> AuthService:
    return AuthService(
        user_repo=user_repo,
        hasher=hasher,
        token_provider=JwtTokenProvider(secret_key=SECRET),
        blacklist_repo=blacklist,
        uow=uow,
        login_limiter=login_limiter,
        client_ip=CLIENT_IP,
        dummy_hash=DUMMY_HASH,
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


def make_service(
    user_repo,
    hasher,
    blacklist,
    uow,
    login_limiter=None,
    client_ip=CLIENT_IP,
    *,
    dummy_hash=DUMMY_HASH,
    token_provider=None,
) -> AuthService:
    return AuthService(
        user_repo=user_repo,
        hasher=hasher,
        token_provider=token_provider or JwtTokenProvider(secret_key=SECRET),
        blacklist_repo=blacklist,
        uow=uow,
        login_limiter=login_limiter or InMemoryLoginAttemptLimiter(),
        client_ip=client_ip,
        dummy_hash=dummy_hash,
    )


class CountingHasher(FakePasswordHasher):
    """비밀번호 검증을 몇 번 했는지 센다"""

    def __init__(self) -> None:
        self.verifies = 0
        self.hashes = 0

    def hash(self, raw_password: str) -> str:
        self.hashes += 1
        return super().hash(raw_password)

    def verify(self, raw_password: str, hashed_password: str) -> bool:
        # 부모 verify는 내부에서 hash()를 불러 해시 횟수가 섞이므로 직접 비교한다
        self.verifies += 1
        return f"hashed:{raw_password}" == hashed_password


class SlowCountingHasher(CountingHasher):
    """검증이 스레드에서 50ms 걸린다. 동시 요청이 겹치게 만든다"""

    def verify(self, raw_password: str, hashed_password: str) -> bool:
        time.sleep(0.05)
        return super().verify(raw_password, hashed_password)


class ReadCountingUserRepository(InMemoryUserRepository):
    def __init__(self) -> None:
        super().__init__()
        self.reads = 0

    async def find_by_email(self, email: Email) -> User | None:
        self.reads += 1
        return await super().find_by_email(email)


class BrokenUserRepository(InMemoryUserRepository):
    async def find_by_email(self, email: Email) -> User | None:
        raise RuntimeError("DB 연결 끊김")


class GatedUserRepository(InMemoryUserRepository):
    """DB 조회의 시작과 완료를 테스트에서 명시적으로 제어한다."""

    def __init__(self, *, broken: bool = False) -> None:
        super().__init__()
        self.started = asyncio.Event()
        self.proceed = asyncio.Event()
        self.broken = broken

    async def find_by_email(self, email: Email) -> User | None:
        self.started.set()
        await self.proceed.wait()
        if self.broken:
            raise RuntimeError("DB 연결 끊김")
        return await super().find_by_email(email)


WRONG = "wrong1234!"


async def fail_login(service: AuthService, email: str, times: int) -> None:
    for _ in range(times):
        with pytest.raises(InvalidCredentialsError):
            await service.login(email, WRONG)


# --- S2: 계정이 없어도 같은 일을 해서 응답 시간으로 가입 여부를 알 수 없게 한다


@pytest.mark.parametrize("account", ["active", "unknown", "inactive"])
async def test_oversized_login_runs_one_bcrypt_check_and_rejects(
    account, user_repo, blacklist, uow, user, monkeypatch
):
    prefix = "가" * 24  # UTF-8로 정확히 72바이트
    stored_hash = bcrypt.hashpw(prefix.encode(), bcrypt.gensalt(rounds=4))
    dummy_hash = bcrypt.hashpw(DUMMY_PASSWORD.encode(), bcrypt.gensalt(rounds=4))
    user.password_hash = stored_hash.decode()
    if account == "inactive":
        user.deleted_at = datetime.now(UTC)
    email = "nobody@example.com" if account == "unknown" else "owner@example.com"
    service = make_service(
        user_repo,
        BcryptPasswordHasher(),
        blacklist,
        uow,
        dummy_hash=dummy_hash.decode(),
    )

    calls = []
    real_checkpw = bcrypt.checkpw
    loop_thread = threading.get_ident()

    def record_check(password, hashed):
        calls.append((len(password), hashed, threading.get_ident()))
        return real_checkpw(password, hashed)

    monkeypatch.setattr(bcrypt, "checkpw", record_check)
    with pytest.raises(InvalidCredentialsError):
        await service.login(email, prefix + "!")

    assert len(calls) == 1
    length, checked_hash, worker_thread = calls[0]
    assert length <= 72
    assert checked_hash == (stored_hash if account == "active" else dummy_hash)
    assert worker_thread != loop_thread


async def test_login_unknown_email_still_runs_password_check(user_repo, blacklist, uow):
    counting = CountingHasher()
    service = make_service(user_repo, counting, blacklist, uow)

    with pytest.raises(InvalidCredentialsError):
        await service.login("nobody@example.com", PASSWORD)

    assert counting.verifies == 1


async def test_login_inactive_user_still_runs_password_check(
    user_repo, blacklist, uow, user
):
    user.deleted_at = datetime.now(UTC)
    counting = CountingHasher()
    service = make_service(user_repo, counting, blacklist, uow)

    with pytest.raises(InvalidCredentialsError):
        await service.login("owner@example.com", PASSWORD)

    assert counting.verifies == 1


async def test_login_unknown_email_does_no_extra_hashing(user_repo, blacklist, uow):
    # 더미 해시는 미리 만들어 둔다. 요청마다 만들면 없는 계정만 스레드 작업을 두 번 기다려
    # 서버가 바쁠 때 응답 시간 차이가 다시 생긴다
    counting = CountingHasher()
    service = make_service(user_repo, counting, blacklist, uow)

    with pytest.raises(InvalidCredentialsError):
        await service.login("nobody@example.com", PASSWORD)

    assert (counting.hashes, counting.verifies) == (0, 1)


async def test_login_with_dummy_password_never_succeeds(
    user_repo, hasher, blacklist, uow, user
):
    user.deleted_at = datetime.now(UTC)
    service = make_service(user_repo, hasher, blacklist, uow)

    for email in ("nobody@example.com", "owner@example.com"):
        with pytest.raises(InvalidCredentialsError):
            await service.login(email, DUMMY_PASSWORD)


# --- S6: 같은 이메일+IP로 15분 안에 5번 틀리면 잠시 막는다


async def test_blocked_attempt_does_not_read_user(blacklist, uow, user):
    repo = ReadCountingUserRepository()
    repo.users[user.id] = user
    service = make_service(repo, CountingHasher(), blacklist, uow)
    await fail_login(service, "owner@example.com", 5)

    with pytest.raises(TooManyLoginAttemptsError):
        await service.login("owner@example.com", PASSWORD)

    assert repo.reads == 5


async def test_concurrent_attempts_cannot_exceed_limit(user_repo, blacklist, uow, user):
    # 확인과 기록 사이에 await가 있으면 동시에 보낸 요청이 모두 확인을 통과한다
    slow = SlowCountingHasher()
    service = make_service(user_repo, slow, blacklist, uow)
    passwords = [WRONG] * 9 + [PASSWORD]  # 마지막에 맞는 비밀번호

    results = await asyncio.gather(
        *(service.login("owner@example.com", pw) for pw in passwords),
        return_exceptions=True,
    )

    assert slow.verifies == 5
    assert sum(isinstance(r, TooManyLoginAttemptsError) for r in results) == 5
    assert not any(hasattr(r, "access_token") for r in results)


async def test_login_success_preserves_four_pending_attempts(
    user_repo, hasher, blacklist, uow, user
):
    now = [0.0]
    limiter = InMemoryLoginAttemptLimiter(clock=lambda: now[0])
    service = make_service(user_repo, hasher, blacklist, uow, limiter)
    repositories = [GatedUserRepository() for _ in range(4)]
    pending = []
    async with asyncio.timeout(5):
        try:
            for repo in repositories:
                repo.users[user.id] = user
                waiting = make_service(repo, hasher, blacklist, uow, limiter)
                pending.append(
                    asyncio.create_task(waiting.login("owner@example.com", WRONG))
                )
            await asyncio.gather(*(repo.started.wait() for repo in repositories))

            now[0] = 901.0  # DB 대기가 길어져도 아직 처리 중인 네 예약은 남는다.
            issued = await service.login("owner@example.com", PASSWORD)
            assert issued.access_token
            await fail_login(service, "owner@example.com", 1)

            with pytest.raises(TooManyLoginAttemptsError):
                await service.login("owner@example.com", WRONG)
        finally:
            for repo in repositories:
                repo.proceed.set()
            results = await asyncio.gather(*pending, return_exceptions=True)

    assert all(isinstance(result, InvalidCredentialsError) for result in results)
    with pytest.raises(TooManyLoginAttemptsError):
        await service.login("owner@example.com", WRONG)


async def test_login_out_of_order_db_error_preserves_later_failures(
    user_repo, hasher, blacklist, uow, user
):
    now = [0.0]
    limiter = InMemoryLoginAttemptLimiter(clock=lambda: now[0])
    service = make_service(user_repo, hasher, blacklist, uow, limiter)
    broken_repo = GatedUserRepository(broken=True)
    broken_service = make_service(broken_repo, hasher, blacklist, uow, limiter)

    async with asyncio.timeout(5):
        broken = asyncio.create_task(
            broken_service.login("owner@example.com", PASSWORD)
        )
        try:
            await broken_repo.started.wait()
            now[0] = 100.0
            await fail_login(service, "owner@example.com", 4)
        finally:
            broken_repo.proceed.set()
            result = await asyncio.gather(broken, return_exceptions=True)

    assert isinstance(result[0], RuntimeError)
    # 가장 오래된 요청만 윈도를 지났다. t=100의 실패 네 번은 모두 남아야 한다.
    now[0] = 901.0
    await fail_login(service, "owner@example.com", 1)
    with pytest.raises(TooManyLoginAttemptsError):
        await service.login("owner@example.com", WRONG)


async def test_cancelled_db_read_returns_its_reservation(hasher, blacklist, uow):
    limiter = InMemoryLoginAttemptLimiter()
    repo = GatedUserRepository()
    service = make_service(repo, hasher, blacklist, uow, limiter)
    async with asyncio.timeout(5):
        pending = asyncio.create_task(service.login("owner@example.com", PASSWORD))
        await repo.started.wait()
        pending.cancel()
        with pytest.raises(asyncio.CancelledError):
            await pending

    assert limiter.tracked_keys() == 0


async def test_cancelled_verification_keeps_reservation_until_worker_finishes(
    user_repo, hasher, blacklist, uow, user, monkeypatch
):
    now = [0.0]
    limiter = InMemoryLoginAttemptLimiter(clock=lambda: now[0])
    service = make_service(user_repo, hasher, blacklist, uow, limiter)
    started = asyncio.Event()
    proceed = asyncio.Event()
    workers = []

    async def gated_to_thread(function, **kwargs):
        if kwargs["raw_password"] == "cancelled-password":
            workers.append(asyncio.current_task())
            started.set()
            await proceed.wait()
        return function(**kwargs)

    # service 모듈은 asyncio를 그대로 쓰므로 이 경로는 전역 asyncio.to_thread를 바꾼다.
    # 테스트가 끝나면 monkeypatch가 되돌린다. 실제 스레드 이동은 다른 테스트가 확인한다
    monkeypatch.setattr("auth.application.service.asyncio.to_thread", gated_to_thread)
    async with asyncio.timeout(5):
        pending = asyncio.create_task(
            service.login("owner@example.com", "cancelled-password")
        )
        try:
            await started.wait()
            pending.cancel()
            with pytest.raises(asyncio.CancelledError):
                await pending
            now[0] = 901.0
            await fail_login(service, "owner@example.com", 4)
            with pytest.raises(TooManyLoginAttemptsError):
                await service.login("owner@example.com", WRONG)
        finally:
            proceed.set()
            await asyncio.gather(*workers, return_exceptions=True)

    with pytest.raises(TooManyLoginAttemptsError):
        await service.login("owner@example.com", WRONG)
    now[0] = 1802.0
    issued = await service.login("owner@example.com", PASSWORD)
    assert issued.access_token


async def test_cancelled_verification_releases_when_worker_fails(
    user_repo, hasher, blacklist, uow, user, monkeypatch
):
    limiter = InMemoryLoginAttemptLimiter()
    service = make_service(user_repo, hasher, blacklist, uow, limiter)
    started = asyncio.Event()
    proceed = asyncio.Event()
    workers = []

    async def failing_to_thread(function, **kwargs):
        workers.append(asyncio.current_task())
        started.set()
        await proceed.wait()
        raise RuntimeError("bcrypt 작업 오류")

    # 위 테스트와 같이 전역 asyncio.to_thread를 테스트 동안만 바꾼다
    monkeypatch.setattr("auth.application.service.asyncio.to_thread", failing_to_thread)
    async with asyncio.timeout(5):
        pending = asyncio.create_task(service.login("owner@example.com", PASSWORD))
        await started.wait()
        pending.cancel()
        with pytest.raises(asyncio.CancelledError):
            await pending
        # 작업이 아직 도는 동안은 슬롯을 유지한다
        assert limiter.tracked_keys() == 1

        proceed.set()
        await asyncio.gather(*workers, return_exceptions=True)
        for _ in range(3):  # 작업 종료 콜백이 실행될 기회를 준다
            await asyncio.sleep(0)

    # 검증 작업 자체가 오류로 끝났으면 비밀번호 실패가 아니므로 예약을 돌려준다
    assert limiter.tracked_keys() == 0


async def test_unexpected_error_is_not_counted_as_failed_login(hasher, blacklist, uow):
    # DB 장애로 실패한 요청까지 세면 장애가 끝나도 사용자가 15분간 막힌다
    limiter = InMemoryLoginAttemptLimiter()
    service = make_service(BrokenUserRepository(), hasher, blacklist, uow, limiter)

    for _ in range(5):
        with pytest.raises(RuntimeError):
            await service.login("owner@example.com", PASSWORD)

    assert limiter.tracked_keys() == 0


async def test_login_blocked_after_five_failures_even_with_correct_password(
    user_repo, blacklist, uow, user
):
    counting = CountingHasher()
    service = make_service(user_repo, counting, blacklist, uow)
    await fail_login(service, "owner@example.com", 5)

    with pytest.raises(TooManyLoginAttemptsError):
        await service.login("owner@example.com", PASSWORD)

    # 막힌 요청은 비밀번호 검증까지 가지 않는다
    assert counting.verifies == 5


class FailingTokenProvider(JwtTokenProvider):
    """비밀번호 검증은 통과했지만 토큰을 만들지 못하는 발급기"""

    def create_access_token(self, user_id):
        raise RuntimeError("토큰 발급기 장애")


async def test_token_issue_failure_keeps_failures_and_returns_its_slot(
    user_repo, hasher, blacklist, uow, user
):
    service = make_service(
        user_repo,
        hasher,
        blacklist,
        uow,
        token_provider=FailingTokenProvider(secret_key=SECRET),
    )
    await fail_login(service, "owner@example.com", 4)

    # 비밀번호는 맞지만 토큰 발급이 실패하면 원래 예외가 그대로 전달된다
    with pytest.raises(RuntimeError, match="토큰 발급기 장애"):
        await service.login("owner@example.com", PASSWORD)

    # 발급 오류는 비밀번호 실패가 아니므로 자기 슬롯을 돌려준다 → 오답 한 번이 더 허용된다
    with pytest.raises(InvalidCredentialsError):
        await service.login("owner@example.com", WRONG)
    # 발급 오류 전의 실패 4건은 지워지지 않았다 → 이제 5건이 차서 막힌다
    with pytest.raises(TooManyLoginAttemptsError):
        await service.login("owner@example.com", WRONG)


async def test_login_block_is_per_client_ip(user_repo, hasher, blacklist, uow, user):
    shared = InMemoryLoginAttemptLimiter()
    attacker = make_service(user_repo, hasher, blacklist, uow, shared, "6.6.6.6")
    owner = make_service(user_repo, hasher, blacklist, uow, shared, "10.0.0.1")
    await fail_login(attacker, "owner@example.com", 5)

    # 다른 IP에서 들어온 계정 주인은 막히지 않는다 (남의 계정을 잠글 수 없음)
    issued = await owner.login("owner@example.com", PASSWORD)

    assert issued.access_token


async def test_login_success_resets_failure_count(
    user_repo, hasher, blacklist, uow, user
):
    service = make_service(user_repo, hasher, blacklist, uow)
    await fail_login(service, "owner@example.com", 4)
    await service.login("owner@example.com", PASSWORD)
    await fail_login(service, "owner@example.com", 4)

    issued = await service.login("owner@example.com", PASSWORD)

    assert issued.access_token


async def test_login_failures_for_unknown_email_are_counted(
    user_repo, hasher, blacklist, uow
):
    service = make_service(user_repo, hasher, blacklist, uow)
    await fail_login(service, "nobody@example.com", 5)

    with pytest.raises(TooManyLoginAttemptsError):
        await service.login("nobody@example.com", WRONG)


async def test_login_failures_count_email_case_insensitively(
    user_repo, hasher, blacklist, uow, user
):
    service = make_service(user_repo, hasher, blacklist, uow)
    await fail_login(service, "Owner@Example.com", 3)
    await fail_login(service, " owner@example.COM ", 2)

    with pytest.raises(TooManyLoginAttemptsError):
        await service.login("owner@example.com", PASSWORD)


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
        login_limiter=InMemoryLoginAttemptLimiter(),
        client_ip=CLIENT_IP,
        dummy_hash=DUMMY_HASH,
    )

    issued = await service.login("owner@example.com", PASSWORD)

    with pytest.raises(UnauthorizedError):
        await service.logout(issued.access_token)
