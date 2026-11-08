# [담당1 - 강성수]

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
    def __init__(self) -> None:
        self.jtis: set[str] = set()

    async def add(self, token: BlackListToken) -> None:
        self.jtis.add(token.jti)

    async def is_blacklisted(self, jti: str) -> bool:
        return jti in self.jtis

    async def cleanup_expired(self, current_time: datetime) -> None:
        pass


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
def service(user_repo, hasher, blacklist) -> AuthService:
    return AuthService(
        user_repo=user_repo,
        hasher=hasher,
        token_provider=JwtTokenProvider(secret_key=SECRET),
        blacklist_repo=blacklist,
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
