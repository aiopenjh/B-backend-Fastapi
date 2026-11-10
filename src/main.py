import asyncio
import os
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI
from auth.infrastructure.repositories import purge_expired_tokens
from auth.presentation.routers.v1.router import router as auth_router
from common.error_handlers import register_error_handlers
from common.logger import get_logger
from common.middleware import register_middleware
from common.database import AsyncSessionLocal, engine
from common.model import init_models, Base
from restaurant.presentation.routers.v1.router import router as restaurant_router
from restaurant.presentation.routers.v1.router import (
    owner_router as restaurant_owner_router,
)
from user.presentation.routers.v1.router import router as user_router
from web import register_web
from owner.presentation.router import router as owner_router
from reservation.presentation.query_router import router as reservation_query_router
from reservation.presentation.router import router as reservation_router
from reservation.presentation.router import admin_router as reservation_admin_router
from reservation.presentation.router import owner_router as reservation_owner_router
from slot.presentation.router import router as slot_router
from seed import seed
from container import run_no_show_loop  # 담당 4: 자동 노쇼 반복

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_models()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    logger.info("tables ensured")
    async with AsyncSessionLocal() as session:
        await seed(session)

    # [담당1] 만료된 로그아웃 토큰(블랙리스트) 정리
    await purge_expired_tokens(AsyncSessionLocal)

    # [담당4] 자동 노쇼: NO_SHOW_CHECK_SECONDS(기본 30초)마다 노쇼 대상을 처리한다. 0이면 끔
    no_show_interval = int(os.getenv("NO_SHOW_CHECK_SECONDS", "30"))
    no_show_task = (
        asyncio.create_task(run_no_show_loop(AsyncSessionLocal, no_show_interval))
        if no_show_interval > 0
        else None
    )

    yield

    if no_show_task is not None:  # 앱을 끌 때 반복을 멈추고 끝날 때까지 기다린다
        no_show_task.cancel()
        with suppress(asyncio.CancelledError):
            await no_show_task
    await engine.dispose()  # 커넥션 풀 반납


app = FastAPI(title="B-backend-Fastapi", lifespan=lifespan)

register_middleware(app)
register_error_handlers(app)

app.include_router(auth_router, prefix="/api/v1")
app.include_router(user_router, prefix="/api/v1")
app.include_router(restaurant_router, prefix="/api/v1")
app.include_router(restaurant_owner_router, prefix="/api/v1")
app.include_router(owner_router, prefix="/api/v1")
app.include_router(reservation_query_router, prefix="/api/v1")
app.include_router(reservation_router, prefix="/api/v1")
app.include_router(reservation_owner_router, prefix="/api/v1")
app.include_router(reservation_admin_router, prefix="/api/v1")
app.include_router(slot_router, prefix="/api/v1")
register_web(app)

from container import wire_dependencies

wire_dependencies(app)
