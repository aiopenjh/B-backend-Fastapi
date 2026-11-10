from enum import unique
from http import HTTPStatus

from common.errors import AppError, ErrorCode, UnauthorizedError


@unique
class AuthErrorCode(ErrorCode):
    TOO_MANY_LOGIN_ATTEMPTS = (
        HTTPStatus.TOO_MANY_REQUESTS,
        "로그인 시도가 너무 많습니다. 잠시 후 다시 시도해 주세요.",
    )


class InvalidCredentialsError(UnauthorizedError):
    """사용자 없음, 탈퇴, 비밀번호 틀림을 구분하지 않는 로그인 실패"""

    message = "이메일 또는 비밀번호가 올바르지 않습니다."


class TooManyLoginAttemptsError(AppError):
    """같은 이메일+IP로 정해진 시간 안에 로그인을 너무 많이 틀림"""

    error_code = AuthErrorCode.TOO_MANY_LOGIN_ATTEMPTS
