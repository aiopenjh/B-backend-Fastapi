# [담당1 - 강성수]
from auth.domain.value_object import AuthenticatedUser


async def get_authenticated_user() -> AuthenticatedUser:
    raise NotImplementedError("get_authenticated_user 의존성이 주입되지 않았습니다.")
