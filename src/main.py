from fastapi import FastAPI

from auth.presentation.routers.v1.router import router as auth_router
from common.error_handlers import register_error_handlers
from common.middleware import register_middleware
from user.presentation.routers.v1.router import router as user_router
from web import register_web

app = FastAPI(title="B-backend-Fastapi")
register_middleware(app)
register_error_handlers(app)

app.include_router(auth_router, prefix="/api/v1")
app.include_router(user_router, prefix="/api/v1")
register_web(app)

