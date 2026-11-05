from dataclasses import dataclass

from fastapi import Query
from pydantic import BaseModel


class Page[T](BaseModel):
    """목록 응답 모양. APIResponse의 data 안에 들어감"""

    items: list[T]
    page: int
    page_size: int
    total: int


@dataclass
class PageParams:
    """몇 페이지를, 한 페이지에 몇 개씩 볼지"""

    page: int = 1
    page_size: int = 20

    @property
    def offset(self) -> int:
        # 앞에서 건너 뛸 개수. 3페이지, 20개씩이면 앞의 40개를 건너뜀
        return (self.page - 1) * self.page_size


def page_params(
    page: int = Query(1, ge=1, description="페이지 번호 (1부터)"),
    page_size: int = Query(
        20, ge=1, le=100, description="한 페이지에 보여 줄 개수 (최대 100)"
    ),
) -> PageParams:
    """주소의 ?page=2&page_size=20을 읽어서 PageParams로 만들어줌 (Depends에 넣어서 씀)"""
    return PageParams(page=page, page_size=page_size)
