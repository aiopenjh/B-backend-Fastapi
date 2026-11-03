from fastapi import Depends, FastAPI

from sqlalchemy.ext.asyncio import AsyncSession
from typing import Annotated

from common.database import get_session
from user.domain.repository import UserRepository
from user.infrastructure.repositories import (
    SQLAlchemyUserRepository,
)

from owner.application.service import OwnerService  # 담당 5: 운영자 매니저


def create_user_repository(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> UserRepository:
    return SQLAlchemyUserRepository(session=session)


def create_owner_service(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> OwnerService:
    return OwnerService(session)
