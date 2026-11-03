from enum import unique
from http import HTTPStatus

from common.errors import AppError, ErrorCode


@unique
class UserErrorCode(ErrorCode):
    INVALID_OLD_PASSWORD = (
        HTTPStatus.BAD_REQUEST,
        "기존 비밀번호가 일치하지 않습니다.",
    )
    SAME_PASSWORD = (
        HTTPStatus.BAD_REQUEST,
        "새 비밀번호는 기존 비밀번호와 달라야 합니다.",
    )


class InvalidOldPasswordError(AppError):
    error_code = UserErrorCode.INVALID_OLD_PASSWORD


class SamePasswordError(AppError):
    error_code = UserErrorCode.SAME_PASSWORD
