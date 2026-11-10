# [담당 5] 화면용 연결: 화면 ↔ 운영자 매니저
"""Jinja2용 조회 어댑터. 기존 서비스를 재사용하고 SQL은 작성하지 않는다."""

from dataclasses import dataclass
from datetime import date
from typing import Annotated, Any

from fastapi import Depends

from auth.domain.value_object import AuthenticatedUser  # 담당 1: 로그인한 사람
from common.errors import AppError  # 공통 오류
from container import (
    create_owner_service,  # 담당 5: 운영자 매니저 공장
    create_user_service,  # 담당 1: 회원 매니저 공장 (예약자 이름)
)
from owner.application.service import OwnerService  # 담당 5: 운영자 매니저
from user.application.service import UserService  # 담당 1: 회원 매니저
from web_auth import UIUser  # 담당 5: 쿠키로 로그인한 사람


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

    def __init__(self, owner: AuthenticatedUser, service: OwnerService, users: UserService | None = None):
        self.owner = owner
        self.service = service
        self.users = users  # 예약자 이름을 꺼낼 때 씀 (담당 1 회원 매니저)

    async def guest_names(self, user_ids: set) -> dict:
        """예약한 사람 번호 → 이름 (한 화면에 최대 몇십 명이라 한 명씩 꺼냄, 탈퇴 등으로 없으면 빈칸)"""
        names = {}
        for user_id in user_ids:
            try:
                names[user_id] = (await self.users.get_user(user_id)).name if self.users else ""
            except AppError:
                names[user_id] = ""
        return names

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
        names = await self.guest_names({reservation.user_id for reservation, _ in rows})
        items = [
            {
                "id": reservation.id,
                "guest_name": names.get(reservation.user_id, ""),
                "starts_at": slot.starts_at,
                "party_size": reservation.party_size,
                "contact_phone": reservation.contact_phone,
                "status": reservation.status,
            }
            for reservation, slot in rows
        ]
        return PageResult(items, total, page, page_size)


def get_owner_ui_queries(
    user: UIUser,
    service: Annotated[OwnerService, Depends(create_owner_service)],
    users: Annotated[UserService, Depends(create_user_service)],
) -> OwnerUIQueries | None:
    """운영자로 로그인했으면 운영자 매니저를 화면용으로 감싸서 준다.

    None이면 로그인 안 했거나 운영자가 아니다 → 화면이 로그인 화면이나 403 안내로 보낸다.
    """
    if user is None or not user.is_owner():
        return None
    return OwnerUIQueries(user, service, users)
