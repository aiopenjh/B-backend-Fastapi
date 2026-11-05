# [담당1 - 강성수]
from typing import Annotated

from fastapi import Depends

from auth.domain.value_object import AuthenticatedUser
from common.errors import ForbiddenError


class NotAdminError(ForbiddenError):
    message = "관리자만 사용할 수 있습니다."


async def get_authenticated_user() -> AuthenticatedUser:
    raise NotImplementedError("get_authenticated_user 의존성이 주입되지 않았습니다.")


async def require_admin(
    user: Annotated[AuthenticatedUser, Depends(get_authenticated_user)],
) -> AuthenticatedUser:
    if not user.is_admin():
        raise NotAdminError()
    return user
