# [담당1 - 강성수]

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
    USER_NOT_FOUND = (HTTPStatus.NOT_FOUND, "사용자를 찾을 수 없습니다.")
    INVALID_ROLE_CHANGE = (HTTPStatus.BAD_REQUEST, "변경할 수 없는 역할입니다.")

    DUPLICATED_USER_ERROR = (HTTPStatus.BAD_REQUEST, "중복된 회원이 등록되어 있습니다.")


class InvalidOldPasswordError(AppError):
    error_code = UserErrorCode.INVALID_OLD_PASSWORD


class SamePasswordError(AppError):
    error_code = UserErrorCode.SAME_PASSWORD


class DuplicatedUserError(AppError):
    error_code = UserErrorCode.DUPLICATED_USER_ERROR


class UserNotFoundError(AppError):
    error_code = UserErrorCode.USER_NOT_FOUND


class InvalidRoleChangeError(AppError):
    error_code = UserErrorCode.INVALID_ROLE_CHANGE
