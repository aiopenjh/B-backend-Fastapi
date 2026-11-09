# [담당 5] 화면용 연결: 화면 ↔ 운영자 매니저
"""Jinja2용 조회 어댑터. 기존 서비스를 재사용하고 SQL은 작성하지 않는다."""

from dataclasses import dataclass
from datetime import date
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from auth.domain.value_object import AuthenticatedUser  # 담당 1: 로그인한 사람
    from owner.application.service import OwnerService


@dataclass
class PageResult:
    items: list[Any]
    total: int
    page: int
    page_size: int

    @property
    def pages(self) -> int:
        return max(1, (self.total + self.page_size - 1) // self.page_size)


class OwnerUIQueries:
    """require_owner를 통과한 사용자와 요청 단위 서비스를 주입받는다."""

    def __init__(self, owner: "AuthenticatedUser", service: "OwnerService"):
        self.owner = owner
        self.service = service

    async def restaurants(self, page: int, page_size: int) -> PageResult:
        from common.pagination import PageParams

        params = PageParams(page=page, page_size=page_size)
        items, total = await self.service.list_my_restaurants(self.owner, params)
        return PageResult(items, total, page, page_size)

    async def reservations(
        self, restaurant_id: int, day: date | None, page: int, page_size: int
    ) -> PageResult:
        from common.pagination import PageParams

        params = PageParams(page=page, page_size=page_size)
        rows, total = await self.service.list_restaurant_reservations(
            self.owner, restaurant_id, day, params
        )
        # 기존 조회 반환값은 (Reservation, TimeSlot) 쌍이다.
        items = [
            {
                "id": reservation.id,
                "starts_at": slot.starts_at,
                "party_size": reservation.party_size,
                "contact_phone": reservation.contact_phone,
                "status": reservation.status,
            }
            for reservation, slot in rows
        ]
        return PageResult(items, total, page, page_size)


def get_owner_ui_queries() -> OwnerUIQueries | None:
    """연결 지점: 인증·미완성 모듈 통합 후 아래 두 의존성을 주입한다.

    owner = Depends(require_owner)
    service = Depends(create_owner_service)
    return OwnerUIQueries(owner, service)

    현재 None은 미연결이며, 빈 조회 결과나 인증 성공을 뜻하지 않는다.
    """
    return None

