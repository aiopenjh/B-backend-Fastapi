# [담당1 - 강성수] User.create 도메인 규칙 테스트
import string

import pytest

from common.errors import InvalidInputError
from user.domain.exceptions import InvalidRoleChangeError
from user.domain.user import Role, User
from user.domain.value_object import Email

VALID_PASSWORD = "abcd1234!"
PASSWORD_ERROR = (
    "비밀번호는 8자 이상 72자 이하이며 영문, 숫자, 특수문자를 하나 이상 포함해야 합니다. "
    "특수문자는 영문 자판의 기호(공백 제외, 예: . _ - ! @ #)를 쓸 수 있습니다."
)


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


@pytest.mark.parametrize("symbol", list(string.punctuation))
def test_create_accepts_any_ascii_symbol(hasher, symbol):
    # 비밀번호 관리자가 만드는 . _ - 같은 기호도 받는다
    user = _create_with_password(hasher, f"abcd1234{symbol}")

    assert user.password_hash == hasher.hash(f"abcd1234{symbol}")


@pytest.mark.parametrize(
    "password",
    [
        "abcd 1234!",  # 공백
        "abcd1234\t!",  # 탭
        "abcd1234！",  # 전각 느낌표 (ASCII 아님 → 72자 = 72바이트가 깨짐)
        "abcd1234•",
        "abcd1234!é",  # 다른 조건은 다 맞고 ASCII가 아닌 글자만 섞임
        "a1!" + "한" * 69,  # 72자지만 210바이트 → bcrypt 한도 초과
        "abcd1234!₩",  # 한글 자판의 ₩는 영문 자판 기호가 아님
    ],
)
def test_create_rejects_whitespace_and_non_ascii_symbols(hasher, password):
    with pytest.raises(InvalidInputError) as exc:
        _create_with_password(hasher, password)

    assert "password" in exc.value.errors


@pytest.mark.parametrize(
    "password",
    [
        "abcd1234",  # 특수문자 없음
        "abcd!!!!",  # 숫자 없음
        "1234!!!!",  # 영문 없음
        "abc123!",  # 7자
    ],
)
def test_create_rejects_password_missing_each_required_kind(hasher, password):
    with pytest.raises(InvalidInputError) as exc:
        _create_with_password(hasher, password)

    assert "password" in exc.value.errors


def test_password_error_message_states_allowed_symbols(hasher):
    with pytest.raises(InvalidInputError) as exc:
        _create_with_password(hasher, "short")

    assert exc.value.errors["password"] == [PASSWORD_ERROR]


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
