# [담당1 - 강성수] container가 로그인 서비스에 요청 IP와 공용 제한기를 넣는지 테스트
import os

# container -> common.database 를 불러올 때 POSTGRES_URL이 필요함 (실제 연결은 하지 않음)
os.environ.setdefault(
    "POSTGRES_URL", "postgresql+asyncpg://test:test@localhost:5432/test"
)

from fastapi.dependencies.utils import get_dependant
from starlette.requests import Request

import container


def make_request(client: tuple[str, int] | None) -> Request:
    return Request({"type": "http", "method": "POST", "headers": [], "client": client})


def build(request: Request):
    return container.create_auth_service(
        request=request,
        user_repo=None,
        blacklist_repo=None,
        token_provider=None,
        uow=None,
    )


def test_fastapi_injects_request_into_auth_service_factory():
    # 위 테스트들은 공장 함수를 직접 불러서, FastAPI가 request를 요청 객체로
    # 알아보는지는 확인하지 못한다. Request import가 빠지면 FastAPI는 request를
    # 필수 쿼리 파라미터로 여겨 모든 로그인이 422가 된다
    dependant = get_dependant(path="/login", call=container.create_auth_service)

    assert dependant.request_param_name == "request"
    assert "request" not in {param.name for param in dependant.query_params}


def test_auth_service_gets_client_ip_from_request():
    service = build(make_request(("203.0.113.7", 51000)))

    assert service.client_ip == "203.0.113.7"


def test_auth_service_without_client_gets_no_ip():
    service = build(make_request(None))

    assert service.client_ip is None


def test_every_request_shares_one_precomputed_dummy_hash():
    # 요청마다 만들면 로그인마다 bcrypt 해시 한 번(약 0.25초)이 더 든다
    first = build(make_request(("203.0.113.7", 1)))
    second = build(make_request(("203.0.113.8", 2)))

    assert first.dummy_hash is second.dummy_hash is container.dummy_password_hash


def test_dummy_hash_costs_the_same_as_real_hashes():
    # 비용(라운드)이 다르면 없는 계정의 검증 시간이 달라져 가입 여부가 드러난다
    real = container.password_hasher.hash("any-password-1!")

    assert container.dummy_password_hash[:7] == real[:7]


def test_every_request_shares_one_login_limiter():
    # 요청마다 새 제한기를 만들면 실패 횟수가 쌓이지 않는다
    first = build(make_request(("203.0.113.7", 1)))
    second = build(make_request(("203.0.113.8", 2)))

    assert first.login_limiter is second.login_limiter
