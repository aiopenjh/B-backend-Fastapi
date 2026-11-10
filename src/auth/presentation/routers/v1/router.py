# [담당1 - 강성수]

from typing import Annotated

from fastapi import APIRouter, Depends, status, Response
from fastapi.security import OAuth2PasswordRequestForm
from auth.application.schemas import TokenResponse
from auth.application.service import AuthService
from auth.presentation.dependencies import auth_service, oauth2_scheme

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


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, summary="로그아웃")
async def logout(
    token: Annotated[str, Depends(oauth2_scheme)],
    service: Annotated[AuthService, Depends(auth_service)],
) -> Response:
    # 블랙리스트에는 토큰 안의 jti 필요, 사용자 대신 토큰 문자열을 받는다.
    await service.logout(token=token)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
