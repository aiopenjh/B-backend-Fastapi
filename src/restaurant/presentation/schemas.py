from pydantic import BaseModel, ConfigDict, Field, model_validator


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


class RestaurantUpdate(BaseModel):
    """식당 수정 입력. 보낸 필드만 바꿈 (모두 선택)"""

    # 기본값 None: 안 보내면 그대로 둠
    # 타입이 str: name, address에 null을 보내면 422 (DB에서 비울 수 없는 칸)
    name: str = Field(None, min_length=1, max_length=150)
    description: str | None = None
    address: str = Field(None, min_length=1, max_length=255)
    phone: str | None = Field(None, max_length=50)

    @model_validator(mode="after")
    def check_not_empty(self):
        """빈 본문({})이면 422"""

        if not self.model_fields_set:
            raise ValueError("수정할 항목을 하나 이상 보내야 합니다.")
        return self


# 담당5(owner)가 쓰는 이름. 팀에서 이름을 정하면 정리
RestaurantOut = RestaurantSummary
