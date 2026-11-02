from fastapi import FastAPI

from common.middleware import register_middleware
from auth.presentation.routers.v1.router import router as auth_router
from user.presentation.routers.v1.router import router as user_router

app = FastAPI(title="B-backend-Fastapi")
register_middleware(app)

app.include_router(auth_router, prefix="/api/v1")
app.include_router(user_router, prefix="/api/v1")
