# [담당3-영민] 슬롯 레포지토리 인터페이스 
from abc import ABC, abstractmethod
from datetime import datetime

from slot.domain.time_slot import TimeSlot

class SlotRepository(ABC):
    
    @abstractmethod
    async def list_for_day(self, restaurant_id: int, start: datetime, end: datetime) -> list[TimeSlot]:
        """인터페이스 선언용 임시 본문. 구현은 SQLAlchemySlotRepository"""
        pass

    @abstractmethod
    async def get_for_update(self, slot_id: int) -> TimeSlot | None:
        """인터페이스 선언용 임시 본문. 구현은 SQLAlchemySlotRepository"""
        pass

    @abstractmethod
    async def save(self, slot: TimeSlot) -> None:
        """인터페이스 선언용 임시 본문. 구현은 SQLAlchemySlotRepository"""
        pass

    @abstractmethod
    async def restaurant_exists(self, restaurant_id: int) -> bool:
        """현재, 임시. restaurant.application 조회 함수 생기면 교체 [담당2-김태양]"""
        pass