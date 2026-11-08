# [담당1 - 강성수]

from typing import Annotated

from fastapi import APIRouter, Depends, status
from fastapi.security import OAuth2PasswordRequestForm
from auth.application.schemas import TokenResponse
from auth.application.service import AuthService
from auth.presentation.dependencies import auth_service

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/login",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
    description="로그인 완료",
)
async def login(
    form: Annotated[OAuth2PasswordRequestForm, Depends()],
    service: Annotated[AuthService, Depends(auth_service)],
) -> TokenResponse:
    # OAuth2 폼은 이메일을 username 필드로 받는다
    issued = await service.login(email=form.username, password=form.password)
    return TokenResponse(access_token=issued.access_token, expires_in=issued.expires_in)

