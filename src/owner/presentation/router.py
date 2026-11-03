#담당 5 운영자 API 창구 : 식당목록
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from common.database import get_session # 공통: DB 통로
from common.schemas import APIResponse # 담당1 : 응답봉투
from common.pagination import Page, PageParams, page_params # 담당 2: 목록 모양페이지
from owner.presentation.dependencies import require_owner # 만든 오너 문
from owner.application.service import OwnerService # 담당 5 : 매니저 (곧 만듦)
from restaurant.presentation.schemas import RestaurantOut # 담당 2 : 식당 응답 모양
from user.domain.user import User # 담당 1 : 회원


router = APIRouter(prefix="/owner", tags=["운영자"], dependencies=[Depends(require_owner)])


@router.get("/restaurants", response_model=APIResponse[Page[RestaurantOut]], summary="내가 운영하는 식당 목록")
async def list_my_restaurants(
    page: PageParams = Depends(page_params),
    owner: User = Depends(require_owner),
    db: AsyncSession = Depends(get_session),
) -> APIResponse[Page[RestaurantOut]]:
    items, total = await OwnerService(db).list_my_restaurants(owner, page)
    return APIResponse.ok(data=Page(
        items=[RestaurantOut.model_validate(r) for r in items],
        page=page.page,
        page_size=page.page_size,
        total=total,
    ))
