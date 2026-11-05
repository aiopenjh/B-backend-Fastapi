# [담당 4] 예약 도메인 예외 : 이미 취소된 예약
from enum import unique
from http import HTTPStatus

from common.errors import AppError, ErrorCode

@unique
class ReservationErrorCode(ErrorCode):
    ALREADY_CANCELLED = (
        HTTPStatus.CONFLICT, "이미 취소된 예약입니다."
    )
class AlreadyCancelledError(AppError):
    error_code = ReservationErrorCode.ALREADY_CANCELLED