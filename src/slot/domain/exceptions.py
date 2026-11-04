# [담당3-영민] TimeSlot 도메인 예외 처리
from enum import unique
from http import HTTPStatus

from common.errors import AppError, ErrorCode


@unique
class SlotErrorCode(ErrorCode):
    SLOT_ALREADY_STARTED = (HTTPStatus.CONFLICT, "이미 시작한 시간대입니다.")
    PARTY_SIZE_EXCEEDED = (HTTPStatus.CONFLICT, "최대 인원을 초과했습니다.")
    SLOT_SOLD_OUT = (HTTPStatus.CONFLICT, "남은 자리가 부족합니다.")


class SlotRuleViolation(AppError):
    status_code = 409


class SlotAlreadyStarted(SlotRuleViolation):
    error_code = SlotErrorCode.SLOT_ALREADY_STARTED


class PartySizeExceeded(SlotRuleViolation):
    error_code = SlotErrorCode.PARTY_SIZE_EXCEEDED


class SlotSoldOut(SlotRuleViolation):
    error_code = SlotErrorCode.SLOT_SOLD_OUT
