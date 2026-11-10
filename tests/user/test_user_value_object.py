# [담당1 - 강성수] user 도메인 VO(Email) 테스트
import dataclasses

import pytest

from common.errors import InvalidInputError
from user.domain.value_object import Email


def test_email_is_trimmed_and_lowercased():
    assert Email("  Alice@Example.COM ").value == "alice@example.com"


def test_invalid_email_raises_input_error_on_email_field():
    with pytest.raises(InvalidInputError) as exc:
        Email("not-an-email")

    assert "email" in exc.value.errors


@pytest.mark.parametrize(
    "raw",
    [
        "a+b@example.com",  # Gmail식 + 주소
        "first.last@sub.example.co.kr",
        "a_b%c-d@example.com",
        "user123@ex-ample.com",
        "a@mail2.example.com",  # 도메인 이름 안의 숫자
        "a@163.com",
        "a" * 64 + "@example.com",  # @ 앞 최대 64자
        "a@" + "b" * 63 + ".com",  # 도메인 이름 한 칸 최대 63자
        "a" * 64 + "@" + ("b" * 61 + ".") * 3 + "com",  # 전체 최대 254자
    ],
)
def test_accepts_common_real_world_emails(raw):
    assert Email(raw).value == raw.lower()


@pytest.mark.parametrize(
    "raw",
    [
        "o'neil@example.com",  # 로컬 부분: 서비스가 받지 않는 기호
        "a!b@example.com",
        "한글@example.com",  # 로컬 부분: ASCII만
        ".a@example.com",  # 로컬 부분: 점으로 시작·끝·연속 불가
        "a.@example.com",
        "a..b@example.com",
        "a@exa_mple.com",  # 도메인: 영문·숫자·하이픈만
        "a@-example.com",
        "a@example-.com",
        "a@example..com",
        "a@example.c",  # 최상위 도메인: 영문 2자 이상
        "a@example.123",
        "a@localhost",
        "a@b@example.com",
        "a b@example.com",
        "a@example.co1",  # 끝까지 맞아야 한다 (fullmatch)
        "a@example.com!",
        "a" * 65 + "@example.com",  # @ 앞 65자
        "a@" + "b" * 64 + ".com",  # 도메인 이름 한 칸 64자
        "a" * 64 + "@" + ("b" * 61 + ".") * 3 + "comx",  # 전체 255자 (DB 컬럼 한도)
        "a" * 300 + "@example.com",
    ],
)
def test_rejects_emails_outside_service_rule(raw):
    with pytest.raises(InvalidInputError) as exc:
        Email(raw)

    assert exc.value.errors == {"email": ["올바른 이메일 형식이 아닙니다."]}


def test_emails_differing_only_in_case_are_equal():
    assert Email("ALICE@example.com") == Email("alice@EXAMPLE.com")


def test_cannot_change_after_creation():
    email = Email("alice@example.com")

    with pytest.raises(dataclasses.FrozenInstanceError):
        email.value = "bob@example.com"  # type: ignore[misc]
