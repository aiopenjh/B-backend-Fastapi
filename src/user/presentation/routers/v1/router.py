# [담당1 - 강성수]

from typing import Annotated

from fastapi import APIRouter, Depends, status

from auth.domain.value_object import AuthenticatedUser
from auth.presentation.dependencies import get_authenticated_user
from common.schemas import APIResponse
from user.application.service import UserService
from user.presentation.dependencies import user_service
from user.presentation.schemas import UserResponse, SignUpUserRequest

router = APIRouter(prefix="/users", tags=["users"])


@router.post(
    "",
    response_model=APIResponse[UserResponse],
    status_code=status.HTTP_201_CREATED,
    summary="회원가입",
)
async def sign_up(
    request: SignUpUserRequest, service: Annotated[UserService, Depends(user_service)]
) -> APIResponse[UserResponse]:
    user = await service.sign_up(
        email=request.email,
        raw_password=request.password,
        name=request.name,
        phone=request.phone,
    )
    return APIResponse.ok(
        data=UserResponse.from_domain(user), message="회원가입이 완료되었습니다."
    )


@router.get(
    "/me",
    response_model=APIResponse[UserResponse],
    status_code=status.HTTP_200_OK,
    summary="내 정보 조회",
)
async def get_me(
    current_user: Annotated[AuthenticatedUser, Depends(get_authenticated_user)],
    service: Annotated[UserService, Depends(user_service)],
) -> APIResponse[UserResponse]:
    user = await service.get_user(user_id=current_user.user_id)
    return APIResponse.ok(data=UserResponse.from_domain(user))
