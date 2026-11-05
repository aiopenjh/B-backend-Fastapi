# [담당1 - 강성수]
from user.application.service import UserService
from user.application.unit_of_work import UnitOfWork
from user.domain.repository import UserRepository


def user_service() -> UserService:
    raise NotImplementedError("UserService 의존성이 주입되지 않았습니다.")


def user_unit_of_work() -> UnitOfWork:
    raise NotImplementedError("UnitOfWork 의존성이 주입되지 않았습니다.")


def user_repository() -> UserRepository:
    raise NotImplementedError("UserRepository 의존성이 주입되지 않았습니다.")
