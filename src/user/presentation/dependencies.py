# [담당1 - 강성수]
from user.application.service import UserService


def user_service() -> UserService:
    raise NotImplementedError("UserService 의존성이 주입되지 않았습니다.")
