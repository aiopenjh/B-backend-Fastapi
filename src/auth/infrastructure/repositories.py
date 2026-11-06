# [담당1 - 강성수]
from datetime import datetime

from sqlalchemy import exists, select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from auth.domain.repository import TokenBlackListRepository
from auth.domain.token_entities import BlackListToken
from auth.infrastructure.models import TokenBlackListModel


class SQLAlchemyTokenBlackListRepository(TokenBlackListRepository):
    def __init__(self, session: AsyncSession):
        self.session = session

    async def add(self, token: BlackListToken) -> None:
        self.session.add(
            TokenBlackListModel(
                user_id=token.user_id,
                token_jti=token.jti,
                expired_at=token.expired_at,
            )
        )

    async def is_blacklisted(self, jti: str) -> bool:
        stmt = select(exists().where(TokenBlackListModel.token_jti == jti))
        return bool(await self.session.scalar(stmt))

    async def cleanup_expired(self, current_time: datetime) -> None:
        stmt = delete(TokenBlackListModel).where(
            TokenBlackListModel.expired_at < current_time
        )
        await self.session.execute(stmt)
