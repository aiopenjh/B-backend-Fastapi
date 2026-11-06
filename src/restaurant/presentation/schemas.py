from pydantic import BaseModel, ConfigDict


class MenuOut(BaseModel):
    """식당 상세 안의 메뉴 하나"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None
    price: int


class RestaurantSummary(BaseModel):
    """식당 목록의 한 줄"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    cuisine: str
    image_url: str | None


class RestaurantDetail(RestaurantSummary):
    """식당 상세 (목록 정보 + 설명, 주소, 전화, 메뉴)"""

    description: str | None
    address: str
    phone: str | None
    menus: list[MenuOut]


# 담당5(owner)가 쓰는 이름. 팀에서 이름을 정하면 정리
RestaurantOut = RestaurantSummary
