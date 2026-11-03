# [담당3-영민] TimeSlot 도메인 예외 처리
from common.errors import AppError

class SlotRuleViolation(AppError):
    status_code = 409

class SlotAlreadyStarted(SlotRuleViolation):
    code = "SLOT_ALREADY_STARTED"

class PartySizeExceeded(SlotRuleViolation):
    code = "PARTY_SIZE_EXCEEDED"

class SlotSoldOut(SlotRuleViolation):
    code = "SLOT_SOLD_OUT"

