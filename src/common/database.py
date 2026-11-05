import os
from collections.abc import AsyncGenerator
from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.exc import SQLAlchemyError
from fastapi import HTTPException, status
from common.logger import get_logger

logger = get_logger(__name__)

POSTGRES_URL = os.getenv("POSTGRES_URL")
if POSTGRES_URL is None:
    raise RuntimeError("POSTGRES_URL 설정값을 채워주세요")

engine = create_async_engine(POSTGRES_URL)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


# 요청 하나당 AsyncSession 하나. commit은 서비스가 함
async def get_session() -> AsyncGenerator[AsyncSession]:
    async with AsyncSessionLocal() as session:
        yield session


# 연결을 호출한 쪽에 넘기고 끝
async def get_conn() -> AsyncGenerator[AsyncConnection]:
    # 연결 시도: 여기서 난 DB 에러만 503으로 변환
    try:
        conn = await engine.connect()
    except SQLAlchemyError as e:
        logger.exception("DB connection failed")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="요청하신 서비스가 잠시 내부적으로 문제가 발생했습니다.",
        ) from None

    try:
        yield conn
    finally:
        await conn.close()
