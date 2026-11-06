from datetime import date, datetime

from pydantic import BaseModel, Field


class SlotOut(BaseModel):
    """시간대 단위 출력 모델"""

    id: int
    starts_at: datetime
    ends_at: datetime
    remaining: int = Field(ge=0)
    max_party_size: int = Field(ge=1)
    available: bool


class AvailabilityOut(BaseModel):
    """특정 식당 날짜의 조회 결과 전체를 담는 모델"""

    restaurant_id: int
    date: date
    slots: list[SlotOut]
