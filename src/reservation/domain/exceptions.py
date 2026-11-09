# [담당 4] 예약 도메인 예외 : 이미 취소된 예약(규칙을 어기면 내는 오류)
from enum import unique
from http import HTTPStatus

from common.errors import AppError, ErrorCode


@unique
class ReservationErrorCode(ErrorCode):
    """예약 에러 코드 목록. (HTTP 상태, 사용자에게 보여 줄 메시지) 짝으로 정한다."""
    ALREADY_CANCELLED = (
        HTTPStatus.CONFLICT, "이미 취소된 예약입니다."
    )
    CANCELLATION_NOT_ALLOWED = (
        HTTPStatus.CONFLICT, "예약 시간이 시작되어 취소할 수 없습니다."
    )
    DUPLICATE_RESERVATION = (
        HTTPStatus.CONFLICT, "이미 예약한 시간대입니다."
    )


class AlreadyCancelledError(AppError):
    """이미 취소된 예약을 또 취소하려 할 때 낸다. 공통 핸들러가 409 응답으로 바꾼다."""
    error_code = ReservationErrorCode.ALREADY_CANCELLED


class CancellationNotAllowedError(AppError):
    """슬롯 시작 시각이 지난 예약을 취소하려 할 때 낸다. 공통 핸들러가 409 응답으로 바꾼다."""
    error_code = ReservationErrorCode.CANCELLATION_NOT_ALLOWED


class DuplicateReservationError(AppError):
    """같은 사용자가 같은 슬롯에 확정 예약을 또 하려 할 때 낸다. 서비스가 exists_confirmed 확인한 뒤 낸다. 공통 핸들러가 409 응답으로 바꾼다."""
    error_code = ReservationErrorCode.DUPLICATE_RESERVATION
