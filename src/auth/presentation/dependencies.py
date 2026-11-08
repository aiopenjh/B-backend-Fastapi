# [담당1 - 강성수]
from typing import Annotated

from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer

from auth.application.service import AuthService
from auth.domain.value_object import AuthenticatedUser
from common.errors import ForbiddenError

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


class NotAdminError(ForbiddenError):
    message = "관리자만 사용할 수 있습니다."


def auth_service() -> AuthService:
    raise NotImplementedError("AuthService 의존성이 주입되지 않았습니다.")


async def get_authenticated_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    service: Annotated[AuthService, Depends(auth_service)],
) -> AuthenticatedUser:
    return await service.authenticate(token=token)


async def require_admin(
    user: Annotated[AuthenticatedUser, Depends(get_authenticated_user)],
) -> AuthenticatedUser:
    if not user.is_admin():
        raise NotAdminError()
    return user
