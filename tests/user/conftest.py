# [담당1 - 강성수] user 테스트 공용 가짜 객체
import pytest

from user.domain.hasher import PasswordHasher


class FakePasswordHasher(PasswordHasher):
    """bcrypt 대신 결과를 예측할 수 있는 가짜 해시"""

    def hash(self, raw_password: str) -> str:
        return f"hashed:{raw_password}"

    def verify(self, raw_password: str, hashed_password: str) -> bool:
        return self.hash(raw_password) == hashed_password


@pytest.fixture
def hasher() -> FakePasswordHasher:
    return FakePasswordHasher()
