from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from common.database import get_session
from owner.application.service import OwnerService  # 담당 5: 운영자 매니저
from user.application.service import UserService
from user.application.unit_of_work import UnitOfWork
from user.domain.hasher import PasswordHasher
from user.domain.repository import UserRepository
from user.infrastructure.repositories import SQLAlchemyUserRepository
from user.infrastructure.security import BcryptPasswordHasher
from user.infrastructure.unit_of_work import SQLAlchemyUnitOfWork

password_hasher: PasswordHasher = BcryptPasswordHasher()


def create_user_repository(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> UserRepository:
    return SQLAlchemyUserRepository(session=session)


def create_unit_of_work(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> UnitOfWork:
    return SQLAlchemyUnitOfWork(session=session)


def create_user_service(
    repo: Annotated[UserRepository, Depends(create_user_repository)],
    uow: Annotated[UnitOfWork, Depends(create_unit_of_work)],
) -> UserService:
    return UserService(
        repo=repo,
        uow=uow,
        hasher=password_hasher,
    )


def create_owner_service(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> OwnerService:
    return OwnerService(session)
