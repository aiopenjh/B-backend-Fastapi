# [담당 5 최지훈] 회원가입 화면 테스트 (가짜 회원 매니저·가짜 로그인 매니저)
import uuid

import httpx
import pytest
from fastapi import FastAPI, Request

from auth.application.service import IssuedToken  # 담당1 로그인 결과
from auth.domain.value_object import AuthenticatedUser, AuthRole  # 담당1 로그인한 사람
from container import create_auth_service, create_user_service
from user.domain.exceptions import DuplicatedUserError  # 담당1 중복 가입
from web import register_web
from web_auth import COOKIE_NAME, get_ui_user

NEW_CUSTOMER = AuthenticatedUser(user_id=uuid.uuid4(), role=AuthRole.CUSTOMER)
GOOD = {"name": "새손님", "email": "new@example.com", "password": "Abcd1234!", "phone": "010-5555-0001"}


class FakeUsers:
    """가짜 회원 매니저: 가입 요청을 적어 두고, taken@example.com은 이미 있는 이메일"""

    def __init__(self):
        self.signed = []

    async def sign_up(self, email, raw_password, name, phone):
        if email == "taken@example.com":
            raise DuplicatedUserError()
        self.signed.append((email, name, phone))


class FakeAuth:
    async def login(self, email, password):
        return IssuedToken(access_token="new-token", expires_in=3600)

    async def authenticate(self, token):
        return NEW_CUSTOMER


def login_as(user):
    def fake(request: Request):
        request.state.ui_user = user
        return user
    return fake


@pytest.fixture
def users():
    return FakeUsers()


def make_client(users, user=None):
    app = FastAPI()
    register_web(app)
    app.dependency_overrides[create_user_service] = lambda: users
    app.dependency_overrides[create_auth_service] = FakeAuth
    app.dependency_overrides[get_ui_user] = login_as(user)
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


async def test_signup_page_and_login_link(users):
    async with make_client(users) as client:
        page = await client.get("/ui/signup")
        login = await client.get("/ui")

    assert page.status_code == 200 and "가입하고 시작하기" in page.text
    assert "/ui/signup" in login.text  # 로그인 화면에 회원가입 링크


async def test_signup_success_logs_in_and_goes_home(users):
    async with make_client(users) as client:
        response = await client.post("/ui/signup", data=GOOD)

    assert response.status_code == 303
    assert response.headers["location"].endswith("/ui/restaurants")  # 손님 첫 화면
    assert response.headers["set-cookie"].startswith(f"{COOKIE_NAME}=new-token")  # 바로 로그인
    assert users.signed == [("new@example.com", "새손님", "010-5555-0001")]


async def test_signup_bad_fields_are_422_with_messages(users):
    async with make_client(users) as client:
        response = await client.post("/ui/signup", data={**GOOD, "password": "abcd", "phone": "abc"})

    assert response.status_code == 422
    assert "비밀번호는 8자 이상" in response.text and "휴대폰 번호 형식이 아니에요" in response.text
    assert 'value="새손님"' in response.text and "abcd" not in response.text  # 적은 값은 남기고 비밀번호는 비움
    assert users.signed == []


async def test_signup_duplicate_email_is_400(users):
    async with make_client(users) as client:
        response = await client.post("/ui/signup", data={**GOOD, "email": "taken@example.com"})

    assert response.status_code == 400
    assert "이미 가입한 이메일이에요." in response.text


async def test_logged_in_user_skips_signup(users):
    async with make_client(users, NEW_CUSTOMER) as client:
        response = await client.get("/ui/signup")

    assert response.status_code == 303
