"""
1. 식당 등록·삭제는 API로 하지 않고 시드 데이터로만 넣는다
2. 식당 정보 수정은 관리자 또는 그 식당의 점주(owner_id가 같은 사용자)만 할 수 있다
3. 예약 기록을 남기기 위해 소프트 삭제(deleted_at)를 하고, 삭제된 식당은 조회되지 않는다
4. 메뉴는 식당에 속하고 가격은 0 이상이다 (메뉴 등록·수정·삭제는 식당 수정과 같은 권한)
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime

from auth.domain.value_object import AuthenticatedUser
from restaurant.domain.exceptions import MenuNotFoundError


@dataclass
class Menu:
    id: int
    name: str
    price: int
    description: str | None = None


@dataclass
class Restaurant:
    id: int
    owner_id: uuid.UUID

    name: str

    address: str
    cuisine: str

    description: str | None = None
    image_url: str | None = None
    phone: str | None = None

    deleted_at: datetime | None = None
    # = [] 로 쓰면 모든 식당이 같은 리스트를 나눠 써서, 식당마다 새 리스트를 만듦
    menus: list[Menu] = field(default_factory=list)

    def is_owned_by(self, user_id: uuid.UUID) -> bool:
        """이 식당의 점주인지 확인"""
        return self.owner_id == user_id

    def is_active(self) -> bool:
        """삭제되지 않은 식당인지 확인"""
        return self.deleted_at is None

    def can_be_edited_by(self, user: AuthenticatedUser) -> bool:
        """관리자는 모든 식당, 운영자는 본인 식당만 수정 가능"""
        return user.is_admin() or (user.is_owner() and self.is_owned_by(user.user_id))

    def find_menu(self, menu_id: int) -> Menu:
        """이 식당의 메뉴 하나. 없거나 다른 식당의 메뉴면 404"""
        for menu in self.menus:
            if menu.id == menu_id:
                return menu
        raise MenuNotFoundError()
