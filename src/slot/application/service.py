from dataclasses import dataclass
from datetime import date

from restaurant.domain.exceptions import RestaurantNotFoundError
from slot.domain.day_range import seoul_day_range, seoul_now
from slot.domain.repository import SlotRepository
from slot.domain.time_slot import TimeSlot


@dataclass(frozen=True)
class SlotAvailability:
    """응용계층의 결과 단위- 도메인 객체 + 이 요청의 인원 기준 판정"""

    slot: TimeSlot
    available: bool


class SlotService:
    def __init__(self, repo: SlotRepository) -> None:
        self.repo = repo

    async def get_availability(
        self, restaurant_id: int, day: date, party_size: int
    ) -> list[SlotAvailability]:
        """유스케이스: 날짜 인원을 고르면 그 식당에서 예약할 수 있는 시간대 보여줌"""

        if not await self.repo.restaurant_exists(restaurant_id):
            raise RestaurantNotFoundError(
                errors={"restaurant_id": [f"id {restaurant_id} 인 식당이 없습니다."]},
            )

        start, end = seoul_day_range(day)
        now = seoul_now()
        slots = await self.repo.list_for_day(restaurant_id, start, end)
        return [
            SlotAvailability(slot=s, available=s.can_accept(party_size, now))
            for s in slots
        ]
