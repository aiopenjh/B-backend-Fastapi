import uuid
from typing import Annotated

import httpx
import pytest
from fastapi import FastAPI, Depends

from auth.application.service import IssuedToken
from auth.domain.exceptions import InvalidCredentialsError
from auth.domain.value_object import AuthenticatedUser, AuthRole
from auth.presentation.dependencies import auth_service, get_authenticated_user
from auth.presentation.routers.v1.router import router
from common.error_handlers import register_error_handlers
from common.errors import UnauthorizedError

LOGIN_URL = "/api/v1/auth/login"
LOGOUT_URL = "/api/v1/auth/logout"
EMAIL = "owner@example.com"
PASSWORD = "abcd1234!"
VALID_TOKEN = "valid-token"
USER_ID = uuid.uuid4()


class StubAuthService:
    """가짜 서비스. 로그인 규칙은 test_auth_service가 검사"""

    async def login(self, email: str, password: str) -> IssuedToken:
        if (email, password) == (EMAIL, PASSWORD):
            return IssuedToken(access_token=VALID_TOKEN, expires_in=3600)

        raise InvalidCredentialsError()

    async def authenticate(self, token: str) -> AuthenticatedUser:
        if token == VALID_TOKEN:
            return AuthenticatedUser(user_id=USER_ID, role=AuthRole.OWNER)

        raise UnauthorizedError()

    async def logout(self, token: str) -> None:
        if token != VALID_TOKEN:
            raise UnauthorizedError()


@pytest.fixture
async def client():
    app = FastAPI()
    register_error_handlers(app=app)
    app.include_router(router, prefix="/api/v1")

    @app.get("/protected")
    async def protected(
        user: Annotated[AuthenticatedUser, Depends(get_authenticated_user)],
    ):
        return {"user_id": str(user.user_id), "role": user.role}

    app.dependency_overrides[auth_service] = StubAuthService

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c


async def test_login_success_returns_oauth2_token_without_envelope(client):
    response = await client.post(
        LOGIN_URL, data={"username": EMAIL, "password": PASSWORD}
    )

    assert response.status_code == 200
    assert response.json() == {
        "access_token": VALID_TOKEN,
        "token_type": "bearer",
        "expires_in": 3600,
    }


async def test_login_fail_wrong_credentials_returns_401_envelope(client):
    response = await client.post(
        LOGIN_URL, data={"username": EMAIL, "password": "wrong1234!"}
    )

    assert response.status_code == 401
    assert response.json()["code"] == "UNAUTHORIZED"


async def test_login_fail_missing_password_returns_422(client):
    response = await client.post(LOGIN_URL, data={"username": EMAIL})

    assert response.status_code == 422


async def test_authenticated_users_success_with_bearer_token(client):
    response = await client.get(
        "/protected", headers={"Authorization": f"Bearer {VALID_TOKEN}"}
    )

    assert response.status_code == 200
    assert response.json() == {"user_id": str(USER_ID), "role": "OWNER"}


async def test_authenticated_user_fail_without_token(client):
    response = await client.get("/protected")

    assert response.status_code == 401
    assert response.json()["code"] == "UNAUTHORIZED"


async def test_authenticated_user_fail_with_invalid_toke(client):
    response = await client.get(
        "/protected", headers={"Authorization": "Bearer not-a-valid-token"}
    )

    assert response.status_code == 401
    assert response.json()["code"] == "UNAUTHORIZED"


async def test_logout_success_returns_204_without_body(client):
    response = await client.post(
        LOGOUT_URL, headers={"Authorization": f"Bearer {VALID_TOKEN}"}
    )

    assert response.status_code == 204
    assert response.content == b""


async def test_logout_fail_without_token_returns_401(client):
    response = await client.post(LOGOUT_URL)

    assert response.status_code == 401
    assert response.json()["code"] == "UNAUTHORIZED"


async def test_logout_fail_with_invalid_token_returns_401(client):
    response = await client.post(
        LOGOUT_URL, headers={"Authorization": "Bearer not-a-valid-token"}
    )

    assert response.status_code == 401
    assert response.json()["code"] == "UNAUTHORIZED"
