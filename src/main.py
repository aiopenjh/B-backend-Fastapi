from fastapi import FastAPI
from contextlib import asynccontextmanager
from auth.presentation.routers.v1.router import router as auth_router
from common.error_handlers import register_error_handlers
from common.middleware import register_middleware
from common.database import engine
from common.model import init_models, Base
from restaurant.presentation.routers.v1.router import router as restaurant_router
from user.presentation.routers.v1.router import router as user_router
from web import register_web


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_models()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield
    await conn.close()


app = FastAPI(title="B-backend-Fastapi", lifespan=lifespan)

register_middleware(app)
register_error_handlers(app)

app.include_router(auth_router, prefix="/api/v1")
app.include_router(user_router, prefix="/api/v1")
app.include_router(restaurant_router, prefix="/api/v1")
register_web(app)

# TODO(담당1): container가 import하는 다른 모듈(reservation·restaurant·slot)이
# dev에 들어오면 아래 두 줄의 주석을 푼다. 지금 풀면 앱이 시작되지 않는다.
# from container import wire_dependencies
# wire_dependencies(app)
