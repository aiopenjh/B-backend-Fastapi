# 담당5 require_owner: 운영자 통과문 만들기
from auth.presentation.dependencies import get_authenticated_user
from fastapi import Depends

from common.errors import ForbiddenError # 담당2 : 403 오류
from auth.domain.value_object import AuthenticatedUser # 담당1 :회원


class NotOwnerError(ForbiddenError):
    message = "운영자만 사용할 수 있습니다."


async def require_owner(user:AuthenticatedUser = Depends(get_authenticated_user)) -> AuthenticatedUser:
    if not user.is_owner():
        raise NotOwnerError()
    return user

