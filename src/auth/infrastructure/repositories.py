# [담당1 - 강성수]
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from datetime import UTC, datetime

from sqlalchemy import exists, select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from auth.domain.repository import TokenBlackListRepository
from auth.domain.token_entities import BLACKLIST_PURGE_GRACE, BlackListToken
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
        # 다른 트랜잭션이 잠근 행은 기다리지 않고 건너뛴다 (SKIP LOCKED).
        # 로그아웃 응답 경로에서 지우므로, 잠금을 기다리면 그만큼 응답이 늦어진다.
        # 건너뛴 행은 다음 정리 때 지워진다
        expired_ids = (
            select(TokenBlackListModel.id)
            .where(TokenBlackListModel.expired_at < current_time)
            .with_for_update(skip_locked=True)
        )
        stmt = delete(TokenBlackListModel).where(
            TokenBlackListModel.id.in_(expired_ids)
        )
        await self.session.execute(stmt)


async def purge_expired_tokens(
    session_factory: Callable[[], AbstractAsyncContextManager[AsyncSession]],
    now: datetime | None = None,
) -> None:
    """만료된 블랙리스트 행을 지우고 확정한다. 앱 시작(lifespan)에서 부른다"""
    cutoff = (now or datetime.now(UTC)) - BLACKLIST_PURGE_GRACE
    async with session_factory() as session:
        repo = SQLAlchemyTokenBlackListRepository(session=session)
        await repo.cleanup_expired(cutoff)
        await session.commit()
