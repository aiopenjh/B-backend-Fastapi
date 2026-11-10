# [담당1 - 강성수]
import uuid
from datetime import UTC, datetime

import httpx
import pytest
from fastapi import FastAPI

from auth.domain.value_object import AuthenticatedUser, AuthRole
from auth.presentation.dependencies import get_authenticated_user
from common.error_handlers import register_error_handlers
from user.domain.exceptions import UserNotFoundError
from user.domain.user import Role, User
from user.domain.value_object import Email
from user.presentation.dependencies import user_service
from user.presentation.routers.v1.router import router

ME_URL = "/api/v1/users/me"
USER_ID = uuid.uuid4()
USER = User(
    id=USER_ID,
    email=Email("alice@example.com"),
    password_hash="hashed:abcd1234!",
    name="고길동",
    phone="010-1234-5678",
    role=Role.CUSTOMER,
    created_at=datetime.now(UTC),
)


class StubUserService:
    """가짜 서비스. 조회 규칙은 test_user_service가 검사"""

    async def get_user(self, user_id: uuid.UUID) -> User:
        if user_id == USER_ID:
            return USER
        raise UserNotFoundError()


@pytest.fixture
def app() -> FastAPI:
    app = FastAPI()
    register_error_handlers(app=app)
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[user_service] = StubUserService
    return app


@pytest.fixture
async def client(app):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c


def login_as(app: FastAPI, user_id: uuid.UUID) -> None:
    """토큰 검사 대신 사용자로 로그인한 것처럼 만든다."""
    app.dependency_overrides[get_authenticated_user] = lambda: AuthenticatedUser(
        user_id=user_id, role=AuthRole.CUSTOMER
    )


async def test_get_me_success_returns_profile_without_password_hash(app, client):
    login_as(app, USER_ID)

    response = await client.get(ME_URL)

    assert response.status_code == 200
    assert response.json()["data"] == {
        "id": str(USER_ID),
        "email": "alice@example.com",
        "name": "고길동",
        "phone": "010-1234-5678",
        "role": "CUSTOMER",
    }
    assert "password_hash" not in response.text
    assert "hashed" not in response.text


async def test_get_me_fail_user_not_found_returns_404(app, client):
    login_as(app, uuid.uuid4())

    response = await client.get(ME_URL)

    assert response.status_code == 404
    assert response.json()["code"] == "USER_NOT_FOUND"


async def test_get_me_fail_without_token_returns_401(client):
    response = await client.get(ME_URL)

    assert response.status_code == 401
    assert response.json()["code"] == "UNAUTHORIZED"


SIGNUP_URL = "/api/v1/users"


async def test_sign_up_with_email_outside_rule_returns_422_with_korean_message(client):
    # 스키마 단계에서 도메인과 같은 문구로 거절된다 (서비스까지 가지 않음)
    response = await client.post(
        SIGNUP_URL,
        json={
            "name": "김철수",
            "email": "o'neil@example.com",
            "password": "abcd1234!",
            "phone": "010-1234-5678",
        },
    )

    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"
    assert response.json()["errors"] == {"email": ["올바른 이메일 형식이 아닙니다."]}
