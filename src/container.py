from fastapi import Depends

from sqlalchemy.ext.asyncio import AsyncSession
from typing import Annotated

from common.database import get_session
from user.application.service import UserService
from user.domain.repository import UserRepository
from user.domain.hasher import PasswordHasher

from user.infrastructure.repositories import SQLAlchemyUserRepository
from user.infrastructure.security import BcryptPasswordHasher

from owner.application.service import OwnerService  # 담당 5: 운영자 매니저

password_hasher: PasswordHasher = BcryptPasswordHasher()


def create_user_repository(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> UserRepository:
    return SQLAlchemyUserRepository(session=session)


def create_user_service(
    repo: Annotated[UserRepository, Depends(create_user_repository)],
) -> UserService:
    return UserService(repo=repo, hasher=password_hasher)


def create_owner_service(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> OwnerService:
    return OwnerService(session)
