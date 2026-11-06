# [담당3-영민] 슬롯 레포지토리 인터페이스 
from abc import ABC, abstractmethod
from datetime import datetime

from slot.domain.time_slot import TimeSlot


class SlotRepository(ABC):
    
    @abstractmethod
    async def list_for_day(self, restaurant_id: int, start: datetime, end: datetime) -> list[TimeSlot]:
        """[start, end) 안에 시작하는 슬롯 — availability 용. 락 없음. starts_at 오름차순."""

    @abstractmethod
    async def get_for_update(self, slot_id: int) -> TimeSlot | None:
        """행 락을 걸고 읽는다 (담당 4 예약·취소). 락은 호출자의 commit/rollback 까지. 없으면 None."""

    @abstractmethod
    async def save(self, slot: TimeSlot) -> None:
        """get_for_update 로 읽은 슬롯의 reserved_guests 를 되돌려 쓴다. flush 까지 — commit 은 서비스."""

    @abstractmethod
    async def restaurant_exists(self, restaurant_id: int) -> bool:
        """현재, 임시. restaurant.application 조회 함수 생기면 교체 [담당2-김태양]"""
