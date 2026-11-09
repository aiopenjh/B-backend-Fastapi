from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Path, Query

from auth.domain.value_object import AuthenticatedUser
from auth.presentation.dependencies import get_authenticated_user
from common.pagination import Page, PageParams, page_params
from common.schemas import APIResponse
from container import create_restaurant_service
from restaurant.application.service import RestaurantService
from restaurant.presentation.schemas import (
    RestaurantDetail,
    RestaurantSummary,
    RestaurantUpdate,
)

# BIGINT 최댓값. 이보다 큰 id는 DB오류(500) 대신 422로 막음
BIGINT_MAX = 9223372036854775807

router = APIRouter(prefix="/restaurants", tags=["식당"])


@router.get(
    "",
    response_model=APIResponse[Page[RestaurantSummary]],
    summary="식당 목록",
)
async def list_restaurants(
    page: Annotated[PageParams, Depends(page_params)],
    service: Annotated[RestaurantService, Depends(create_restaurant_service)],
    q: Annotated[str | None, Query(description="식당 이름 검색어")] = None,
    cuisine: Annotated[str | None, Query(description="음식 종류")] = None,
    sort: Annotated[Literal["id", "name"], Query(description="정렬 기준")] = "id",
) -> APIResponse[Page[RestaurantSummary]]:
    restaurants, total = await service.list_restaurants(q, cuisine, sort, page)
    return APIResponse.ok(
        data=Page(
            items=[RestaurantSummary.model_validate(r) for r in restaurants],
            page=page.page,
            page_size=page.page_size,
            total=total,
        )
    )


@router.get(
    "/{restaurant_id}",
    response_model=APIResponse[RestaurantDetail],
    summary="식당 상세",
)
async def get_restaurant(
    restaurant_id: Annotated[int, Path(ge=1, le=BIGINT_MAX, description="식당 id")],
    service: Annotated[RestaurantService, Depends(create_restaurant_service)],
) -> APIResponse[RestaurantDetail]:
    restaurant = await service.get_restaurant(restaurant_id)
    return APIResponse.ok(data=RestaurantDetail.model_validate(restaurant))


@router.patch(
    "/{restaurant_id}",
    response_model=APIResponse[RestaurantDetail],
    summary="식당 수정 (관리자 또는 본인 식당 운영자)",
)
async def update_restaurant(
    restaurant_id: Annotated[int, Path(ge=1, le=BIGINT_MAX, description="식당 id")],
    body: RestaurantUpdate,
    user: Annotated[AuthenticatedUser, Depends(get_authenticated_user)],
    service: Annotated[RestaurantService, Depends(create_restaurant_service)],
) -> APIResponse[RestaurantDetail]:
    restaurant = await service.update_restaurant(
        user, restaurant_id, body.model_dump(exclude_unset=True)
    )
    return APIResponse.ok(data=RestaurantDetail.model_validate(restaurant))
