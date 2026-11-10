# [담당1 - 강성수] 회원가입 요청 스키마 테스트
import pytest
from pydantic import ValidationError

from user.presentation.schemas import SignUpUserRequest


def _request(password: str) -> dict:
    return {
        "name": "김철수",
        "email": "alice@example.com",
        "password": password,
        "phone": "010-1234-5678",
    }


def test_signup_request_accepts_72_char_password():
    SignUpUserRequest(**_request("a1!" + "a" * 69))


def test_signup_request_rejects_password_over_72_chars():
    with pytest.raises(ValidationError) as exc:
        SignUpUserRequest(**_request("a1!" + "a" * 70))

    assert exc.value.errors()[0]["loc"] == ("password",)
