# [담당1 - 강성수]
import uuid

from user.domain.repository import UserRepository
from sqlalchemy.ext.asyncio import AsyncSession

from user.domain.user import User
from user.domain.value_object import Email


class SQLAlchemyUserRepository(UserRepository):

    def __init__(self, session: AsyncSession):
        self.session = session

    async def find_by_id(self, user_id: uuid.UUID) -> User | None:
        raise NotImplementedError

    async def find_by_email(self, email: Email) -> User | None:
        raise NotImplementedError

    async def save(self, user: User) -> User:
        raise NotImplementedError
