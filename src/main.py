from fastapi import FastAPI
from contextlib import asynccontextmanager
from auth.presentation.routers.v1.router import router as auth_router
from common.error_handlers import register_error_handlers
from common.logger import get_logger
from common.middleware import register_middleware
from common.database import engine
from common.model import init_models, Base
from restaurant.presentation.routers.v1.router import router as restaurant_router
from user.presentation.routers.v1.router import router as user_router
from web import register_web
from owner.presentation.router import router as owner_router
from reservation.presentation.query_router import router as reservation_query_router
from slot.presentation.router import router as slot_router

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_models()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    logger.info("tables ensured")

    yield
    await engine.dispose()  # 커넥션 풀 반납


app = FastAPI(title="B-backend-Fastapi", lifespan=lifespan)

register_middleware(app)
register_error_handlers(app)

app.include_router(auth_router, prefix="/api/v1")
app.include_router(user_router, prefix="/api/v1")
app.include_router(restaurant_router, prefix="/api/v1")
app.include_router(owner_router, prefix="/api/v1")
app.include_router(reservation_query_router, prefix="/api/v1")
app.include_router(slot_router, prefix="/api/v1")
register_web(app)

from container import wire_dependencies

wire_dependencies(app)
