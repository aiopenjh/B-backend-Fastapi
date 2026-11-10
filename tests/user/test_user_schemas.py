# [담당1 - 강성수] 회원가입 요청 스키마 테스트
import pytest
from pydantic import ValidationError

from user.presentation.schemas import SignUpUserRequest

EMAIL_ERROR = "올바른 이메일 형식이 아닙니다."


def _request(password: str = "abcd1234!", email: str = "alice@example.com") -> dict:
    return {
        "name": "김철수",
        "email": email,
        "password": password,
        "phone": "010-1234-5678",
    }


def test_signup_request_accepts_72_char_password():
    SignUpUserRequest(**_request("a1!" + "a" * 69))


def test_signup_request_rejects_password_over_72_chars():
    with pytest.raises(ValidationError) as exc:
        SignUpUserRequest(**_request("a1!" + "a" * 70))

    assert exc.value.errors()[0]["loc"] == ("password",)


def test_signup_request_accepts_plus_address():
    request = SignUpUserRequest(**_request(email="a+b@example.com"))

    assert request.email == "a+b@example.com"


@pytest.mark.parametrize(
    "email",
    [
        "o'neil@example.com",  # 표준 검사기(EmailStr)는 받지만 서비스 규칙은 받지 않음
        "a@exa_mple.com",
        "a" * 300 + "@example.com",  # 길이 제한도 도메인과 같다 (DB 컬럼 255자)
    ],
)
def test_signup_request_uses_the_same_email_rule_and_message_as_domain(email):
    # 스키마와 도메인이 다르면 스키마를 통과한 값이 서비스에서 다시 거절된다
    with pytest.raises(ValidationError) as exc:
        SignUpUserRequest(**_request(email=email))

    error = exc.value.errors()[0]
    assert error["loc"] == ("email",)
    assert EMAIL_ERROR in error["msg"]


def test_signup_request_rejects_non_string_email_as_validation_error():
    # 문자열 검사가 먼저 돌아야 한다. 아니면 Email(123)에서 500이 난다
    with pytest.raises(ValidationError) as exc:
        SignUpUserRequest(**{**_request(), "email": 123})

    assert exc.value.errors()[0]["loc"] == ("email",)


def test_signup_email_is_documented_as_email_format():
    schema = SignUpUserRequest.model_json_schema()["properties"]["email"]

    assert (schema["type"], schema["format"]) == ("string", "email")
