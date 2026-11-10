# [담당 4] 예약 도메인 예외 : 취소·노쇼·입장 확인 규칙을 어기면 내는 오류
from enum import unique
from http import HTTPStatus

from common.errors import AppError, ErrorCode


@unique
class ReservationErrorCode(ErrorCode):
    """예약 에러 코드 목록. (HTTP 상태, 사용자에게 보여 줄 메시지) 짝으로 정한다."""

    ALREADY_CANCELLED = (HTTPStatus.CONFLICT, "이미 취소된 예약입니다.")
    CANCELLATION_NOT_ALLOWED = (
        HTTPStatus.CONFLICT,
        "예약 시간이 시작되어 취소할 수 없습니다.",
    )
    DUPLICATE_RESERVATION = (HTTPStatus.CONFLICT, "이미 예약한 시간대입니다.")
    ALREADY_CHECKED_IN = (HTTPStatus.CONFLICT, "이미 입장 확인된 예약입니다.")
    CHECK_IN_NOT_ALLOWED = (HTTPStatus.CONFLICT, "지금은 입장 확인을 할 수 없습니다.")
    NO_SHOW_TOO_EARLY = (HTTPStatus.CONFLICT, "아직 노쇼로 처리할 수 없습니다.")
    CANCEL_REASON_NOT_ALLOWED = (
        HTTPStatus.UNPROCESSABLE_CONTENT,
        "이 취소 이유는 사용할 수 없습니다.",
    )
    CANCEL_NOTE_REQUIRED = (
        HTTPStatus.UNPROCESSABLE_CONTENT,
        "취소 메모를 입력해 주세요.",
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


class AlreadyCheckedInError(AppError):
    """이미 입장 확인된 예약을 또 입장 확인하거나 노쇼로 처리하려 할 때 낸다 (409)."""

    error_code = ReservationErrorCode.ALREADY_CHECKED_IN


class CheckInNotAllowedError(AppError):
    """입장 확인 시간(시작 30분 전 ~ 끝나기 전)이 아닐 때 낸다 (409)."""

    error_code = ReservationErrorCode.CHECK_IN_NOT_ALLOWED


class NoShowTooEarlyError(AppError):
    """시작 시각 + 유예 시간이 지나기 전에 노쇼로 처리하려 할 때 낸다 (409)."""

    error_code = ReservationErrorCode.NO_SHOW_TOO_EARLY


class CancelReasonNotAllowedError(AppError):
    """취소한 사람의 역할에 맞지 않는 취소 이유일 때 낸다 (422)."""

    error_code = ReservationErrorCode.CANCEL_REASON_NOT_ALLOWED


class CancelNoteRequiredError(AppError):
    """관리자가 메모 없이 취소하려 할 때 낸다 (422)."""

    error_code = ReservationErrorCode.CANCEL_NOTE_REQUIRED
