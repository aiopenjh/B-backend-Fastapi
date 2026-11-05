# [담당1 - 강성수] UserService.signUp 테스트 (메모리 레포지토리 사용)
import uuid

import pytest

from common.errors import InvalidInputError
from user.application.service import UserService
from user.application.unit_of_work import ConflictError, UnitOfWork
from user.domain.exceptions import DuplicatedUserError
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


async def test_sign_up_saves_user_with_normalized_email(service, repo):
    user = await service.signUp(
        "  Alice@Example.COM ", VALID_PASSWORD, "김철수", "010-1234-5678"
    )

    assert user.email == Email("alice@example.com")
    assert user.id is not None
    assert await repo.find_by_email(Email("alice@example.com")) is user


async def test_sign_up_rejects_email_already_registered_ignoring_case(service, repo):
    await service.signUp("alice@example.com", VALID_PASSWORD, "김철수", "010-1234-5678")

    with pytest.raises(DuplicatedUserError):
        await service.signUp(
            "ALICE@example.com", VALID_PASSWORD, "김영희", "010-9876-5432"
        )

    assert len(repo.users) == 1


async def test_sign_up_with_invalid_email_saves_nothing(service, repo):
    with pytest.raises(InvalidInputError):
        await service.signUp("not-an-email", VALID_PASSWORD, "김철수", "010-1234-5678")

    assert repo.users == {}


async def test_sign_up_commits_once(service, uow):
    await service.signUp("alice@example.com", VALID_PASSWORD, "고길동", "010-1234-5678")

    assert uow.commits == 1


async def test_rejected_sign_up_does_not_commit(service, uow):
    with pytest.raises(InvalidInputError):
        await service.signUp("not-an-email", VALID_PASSWORD, "고길동", "010-1234-5678")

    assert uow.commits == 0


async def test_conflict_at_commit_becomes_duplicated_user(repo, hasher):
    service = UserService(repo=repo, uow=FakeUnitOfWork(conflict=True), hasher=hasher)

    with pytest.raises(DuplicatedUserError):
        await service.signUp("test@test.org", VALID_PASSWORD, "고길동", "010-1234-5678")


