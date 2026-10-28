import logging
import os
from collections.abc import AsyncIterator

from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import create_async_engine, AsyncConnection
from sqlalchemy.exc import SQLAlchemyError
from fastapi import HTTPException, status

load_dotenv()

logger = logging.getLogger(__name__)

POSTGRES_URL = os.getenv("POSTGRES_URL")
if POSTGRES_URL is None:
    raise RuntimeError("POSTSQL_URL 설정값을 채워주세요")

engine = create_async_engine(POSTGRES_URL)


# 연결을 호출한 쪽에 넘기고 끝
async def get_conn() -> AsyncIterator[AsyncConnection]:
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
