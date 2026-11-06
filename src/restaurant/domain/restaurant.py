"""
1. 식당 등록·삭제는 API로 하지 않고 시드 데이터로만 넣는다
2. 식당 정보 수정은 관리자 또는 그 식당의 점주(owner_id가 같은 사용자)만 할 수 있다
3. 예약 기록을 남기기 위해 소프트 삭제(deleted_at)를 하고, 삭제된 식당은 조회되지 않는다
4. 메뉴는 식당에 속하고 가격은 0 이상이다 (메뉴 등록·수정·삭제는 추후 구현)
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime


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

    # Todo: 메뉴 등록/수정/삭제는 나머지 구현 후에 추가 예정
    # """
    # 1. 메뉴 등록/수정/삭제는 점주만 가능
    # 2. 운영 중인 업체만 가능
    # """

    # def add_menu(self, name: str, price: int, description: str):
    #     self.check_owner()  # 점주인지 체크

    #     self.menus.append(Menu(name=name, price=price, description=description))

    # def remove_menu(self, id: int):
    #     self.check_owner()
    #     self.menus = [menu for menu in self.menus if menu.id != id]

    # def replace_menu(self, id: int, replacement: Menu):
    #     self.check_owner()
    #     for i, menu in enumerate(self.menus):
    #         if menu.id == id:
    #             self.menus[i] = replacement

    def is_owned_by(self, user_id: uuid.UUID) -> bool:
        """이 식당의 점주인지 확인"""
        return self.owner_id == user_id

    def is_active(self) -> bool:
        """삭제되지 않은 식당인지 확인"""
        return self.deleted_at is None
