# [담당1 - 강성수] UserModel -> User 변환 테스트 (DB 없이 객체만 사용)
import uuid
from datetime import UTC, datetime

from user.domain.user import Role
from user.domain.value_object import Email
from user.infrastructure.models import UserModel

NOW = datetime(2026, 11, 4, 3, 0, tzinfo=UTC)


def test_to_user_converts_db_values_to_domain_types():
    user_id = uuid.uuid4()
    model = UserModel(
        id=user_id,
        email="alice@example.com",
        name="김철수",
        password_hash="hashed",
        phone="010-1234-5678",
        role="OWNER",
        created_at=NOW,
    )

    user = model.to_user()

    assert user.id == user_id
    assert user.email == Email("alice@example.com")
    assert user.role is Role.OWNER
    assert user.created_at == NOW
    assert user.deleted_at is None
