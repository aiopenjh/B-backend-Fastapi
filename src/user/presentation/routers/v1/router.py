# [담당1 - 강성수]

from typing import Annotated

from fastapi import APIRouter, Depends, status

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
    user = await service.signUp(
        email=request.email,
        raw_password=request.password,
        name=request.name,
        phone=request.phone,
    )
    return APIResponse.ok(
        data=UserResponse.from_domain(user), message="회원가입이 완료되었습니다."
    )
