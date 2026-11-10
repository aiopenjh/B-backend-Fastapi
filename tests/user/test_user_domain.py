# [담당1 - 강성수] User.create 도메인 규칙 테스트
import pytest

from common.errors import InvalidInputError
from user.domain.exceptions import InvalidRoleChangeError
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


def _create_with_password(hasher, raw_password: str) -> User:
    return User.create(
        email=Email("alice@example.com"),
        raw_password=raw_password,
        name="김철수",
        phone="010-1234-5678",
        hasher=hasher,
    )


def test_create_accepts_72_char_password(hasher):
    user = _create_with_password(hasher, "a1!" + "a" * 69)

    assert user.password_hash == hasher.hash("a1!" + "a" * 69)


def test_create_rejects_password_over_72_chars(hasher):
    with pytest.raises(InvalidInputError) as exc:
        _create_with_password(hasher, "a1!" + "a" * 70)

    assert "password" in exc.value.errors


@pytest.mark.parametrize(
    "password",
    [
        "a!" + "１" * 70,  # 전각 숫자: 72자지만 212바이트 → bcrypt 한도 초과
        "abcd١٢٣٤!",  # 아랍 숫자도 \d에는 걸린다
    ],
)
def test_create_rejects_non_ascii_digits(hasher, password):
    with pytest.raises(InvalidInputError) as exc:
        _create_with_password(hasher, password)

    assert "password" in exc.value.errors


def test_create_rejects_password_with_trailing_newline(hasher):
    with pytest.raises(InvalidInputError) as exc:
        _create_with_password(hasher, VALID_PASSWORD + "\n")

    assert "password" in exc.value.errors


def _user_with_role(hasher, role: Role) -> User:
    user = _create_with_password(hasher, VALID_PASSWORD)
    user.role = role
    return user


def test_change_owner_role_stores_role_enum_from_plain_string(hasher):
    user = _user_with_role(hasher, Role.CUSTOMER)

    user.change_owner_role("OWNER")

    assert user.role is Role.OWNER
    assert user.updated_at is not None


def test_change_owner_role_same_role_given_as_string_is_noop(hasher):
    user = _user_with_role(hasher, Role.CUSTOMER)

    user.change_owner_role("CUSTOMER")

    assert user.role is Role.CUSTOMER
    assert user.updated_at is None


@pytest.mark.parametrize("bad_role", ["ADMIN", "UNKNOWN"])
def test_change_owner_role_rejects_unassignable_role(hasher, bad_role):
    user = _user_with_role(hasher, Role.CUSTOMER)

    with pytest.raises(InvalidRoleChangeError):
        user.change_owner_role(bad_role)


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
