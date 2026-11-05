# [담당1 - 강성수]
import uuid
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from user.domain.repository import UserRepository
from user.domain.user import User
from user.domain.value_object import Email
from user.infrastructure.models import UserModel


class SQLAlchemyUserRepository(UserRepository):

    def __init__(self, session: AsyncSession):
        self.session = session

    async def find_by_id(self, user_id: uuid.UUID) -> User | None:
        stmt = select(UserModel).where(UserModel.id == user_id)
        user_model = await self.session.scalar(stmt)
        return user_model.to_user() if user_model else None

    async def find_by_email(self, email: Email) -> User | None:
        stmt = select(UserModel).where(UserModel.email == email.value)
        user_model = await self.session.scalar(stmt)
        return user_model.to_user() if user_model else None

    async def save(self, user: User) -> User:
        user_model = UserModel(
            id=user.id,
            email=user.email.value,
            name=user.name,
            password_hash=user.password_hash,
            phone=user.phone,
            role=user.role.value,
            created_at=user.created_at,
        )
        self.session.add(user_model)
        return user
