# [담당1 - 강성수] User.create 도메인 규칙 테스트
import pytest

from common.errors import InvalidInputError
from user.domain.user import Role, User
from user.domain.value_object import Email

VALID_PASSWORD = "abcd1234!"


def test_create_stores_hash_not_raw_password(hasher):
    user = User.create(
        email=Email("alice@example.com"),
        raw_password=VALID_PASSWORD,
        name="김철수",
        phone="010-1234-5678",
        hasher=hasher,
    )

    assert user.password_hash == hasher.hash(VALID_PASSWORD)
    assert user.password_hash != VALID_PASSWORD


def test_new_user_is_customer_with_identity(hasher):
    user = User.create(
        email=Email("alice@example.com"),
        raw_password=VALID_PASSWORD,
        name="김철수",
        phone="010-1234-5678",
        hasher=hasher,
    )

    assert user.role is Role.CUSTOMER
    assert user.id is not None


def test_create_rejects_weak_password(hasher):
    with pytest.raises(InvalidInputError) as exc:
        User.create(
            email=Email("alice@example.com"),
            raw_password="short",
            name="김철수",
            phone="010-1234-5678",
            hasher=hasher,
        )

    assert "password" in exc.value.errors


def test_create_rejects_name_out_of_range(hasher):
    with pytest.raises(InvalidInputError) as exc:
        User.create(
            email=Email("alice@example.com"),
            raw_password=VALID_PASSWORD,
            name="김",
            phone="010-1234-5678",
            hasher=hasher,
        )

    assert "name" in exc.value.errors
