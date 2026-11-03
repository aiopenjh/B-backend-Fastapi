import uuid

from user.domain.repository import UserRepository
from sqlalchemy.ext.asyncio import AsyncSession

from user.domain.user import User


class SQLAlchemyUserRepository(UserRepository):

    def __init__(self, session: AsyncSession):
        self.session = session

    async def find_by_id(self, user_id: uuid.UUID) -> User | None:
        raise NotImplementedError

    async def find_by_email(self, email: str) -> User | None:
        raise NotImplementedError

    async def save(self, user: User) -> User:
        raise NotImplementedError
