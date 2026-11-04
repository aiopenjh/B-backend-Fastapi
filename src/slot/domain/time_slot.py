# [담당3-영민] TimeSlot 도메인 구현
from dataclasses import dataclass
from datetime import datetime

from slot.domain.exceptions import (
    PartySizeExceeded,
    SlotAlreadyStarted,
    SlotRuleViolation,
    SlotSoldOut,
)

# timeslot 정의


@dataclass
class TimeSlot:
    id: int
    restaurant_id: int
    starts_at: datetime
    ends_at: datetime
    capacity: int
    reserved_guests: int
    max_party_size: int

    def __post_init__(self) -> None:
        if self.starts_at.tzinfo is None or self.ends_at.tzinfo is None:
            raise ValueError("starts_at/ends_at must be timezone aware")
        if self.starts_at >= self.ends_at:
            raise ValueError("starts_at must be before ends_at")
        if self.capacity < 0 or not 0 <= self.reserved_guests <= self.capacity:
            raise ValueError("0 <= reserved_guests <= capacity required")
        if self.max_party_size < 1:
            raise ValueError("max_party_size must be >= 1")

    # ---- 남은 좌석 수, 시간 조건 ----

    @property
    def remaining(self) -> int:
        return self.capacity - self.reserved_guests

    def has_started(self, now: datetime) -> bool:
        return now >= self.starts_at

    # ---- 요청 판정 — can_accept 와 reserve 가 같은 _violation 을 쓴다 ----

    def _violation(self, party_size: int, now: datetime) -> SlotRuleViolation | None:
        if party_size < 1:
            raise ValueError("party_size must be >= 1")
        if self.has_started(now):
            return SlotAlreadyStarted(
                errors={"slot_id": [f"{self.starts_at.isoformat()} 에 시작한 시간대입니다."]}
            )
        if party_size > self.max_party_size:
            return PartySizeExceeded(
                errors={
                    "party_size": [
                        f"1회 최대 {self.max_party_size}명까지 예약할 수 있습니다. 요청: {party_size}명"
                    ]
                }
            )
        if party_size > self.remaining:
            return SlotSoldOut(
                errors={
                    "party_size": [
                        f"남은 자리({self.remaining}명)보다 많습니다. 요청: {party_size}명"
                    ]
                },
            )
        return None

    def can_accept(self, party_size: int, now: datetime) -> bool:
        return self._violation(party_size, now) is None

    # ---- 상태 변경 — reserved_guests 를 바꾸는 유일한 두 메서드 ----

    def reserve(self, party_size: int, now: datetime) -> None:
        """담당4(민지님)가 행 락을 잡은 뒤 부르는 메서드"""
        if (violation := self._violation(party_size, now)) is not None:
            raise violation

        self.reserved_guests += party_size

    def release(self, party_size: int) -> None:
        """취소 시 좌석 복구, 담당4(민지님) Reservation.cancel() 다음에 호출"""
        if party_size < 1 or party_size > self.reserved_guests:
            raise ValueError("cannot release more than reserved")
        self.reserved_guests -= party_size
