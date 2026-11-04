from user.domain.user import User


async def get_current_user() -> User:
    raise NotImplementedError("get_current_user 의존성이 주입되지 않았습니다.")
