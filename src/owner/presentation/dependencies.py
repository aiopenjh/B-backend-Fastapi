# 담당5 requre_owner: 운영자 통과문 만들기
from fastapi import Depends

from common.errors import ForbiddenError # 담당2 : 403 오류
from user.domain.user import User, Role # 담당1 :회원
from user.presentation.dependencies import get_current_user # 담당 1: 누구냐!!


class NotOwnerError(ForbiddenError):
    message = "운영자만 사용할 수 있습니다."


async def require_owner(user: User = Depends(get_current_user)) -> User:
    if user.role!=Role.OWNER:
        raise NotOwnerError()
    return user

