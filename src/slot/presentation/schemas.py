from datetime import date, datetime
from typing import Annotated

from pydantic import BaseModel, Field


class SlotOut(BaseModel):
    """시간대 단위 출력 모델"""

    id: Annotated[int, Field(description="예약 슬롯 고유 ID")]
    starts_at: Annotated[
        datetime,
        Field(description="슬롯 시작 시간(서울시간)"),
    ]
    ends_at: Annotated[
        datetime,
        Field(description="슬롯 종료 시간(서울시간"),
    ]
    remaining: Annotated[
        int,
        Field(ge=0, description="슬롯 남은 인원 수"),
    ]
    max_party_size: Annotated[
        int,
        Field(ge=1, description="한 번 예약으로 신청가능한 최대 인원 수"),
    ]
    available: Annotated[
        bool,
        Field(description="예약 가능 여부"),
    ]


class AvailabilityOut(BaseModel):
    """특정 식당 날짜의 조회 결과 전체를 담는 모델"""

    restaurant_id: Annotated[
        int,
        Field(description="조회한 식당 고유 ID"),
    ]
    date: Annotated[
        date,
        Field(description="조회 날짜(서울시간)"),
    ]
    slots: Annotated[
        list[SlotOut],
        Field(description="슬롯별 조회 결과"),
    ]
