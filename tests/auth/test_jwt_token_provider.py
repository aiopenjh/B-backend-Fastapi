# [담당1 - 강성수]
import uuid

import jwt
import pytest

from auth.infrastructure.security import JwtTokenProvider
from common.errors import UnauthorizedError

SECRET = "k" * 64  # HS512 최소 길이(64바이트) 테스트용 키

monkeypatch = pytest.MonkeyPatch


@pytest.fixture
def provider() -> JwtTokenProvider:
    return JwtTokenProvider(secret_key=SECRET)


def test_decode_success_returns_same_user_and_jti(provider):
    user_id = uuid.uuid4()

    token, jti, expired_at, _ = provider.create_access_token(user_id=user_id)
    payload = provider.decode_token(token=token)

    assert payload.user_id == user_id
    assert payload.jti == jti
    assert payload.exp == expired_at


def test_create_token_success_expires_in_is_seconds():
    provider = JwtTokenProvider(secret_key=SECRET, access_token_expire_minutes=30)

    _, _, _, expires_in = provider.create_access_token(user_id=uuid.uuid4())

    assert expires_in == 30 * 60


def test_create_token_success_jti_is_unique(provider):
    user_id = uuid.uuid4()

    _, first_jti, _, _ = provider.create_access_token(user_id=user_id)
    _, second_jti, _, _ = provider.create_access_token(user_id=user_id)

    assert first_jti != second_jti


def test_decode_fail_expired_token():
    provider = JwtTokenProvider(secret_key=SECRET, access_token_expire_minutes=-1)
    token, *_ = provider.create_access_token(user_id=uuid.uuid4())

    with pytest.raises(UnauthorizedError):
        provider.decode_token(token=token)


def test_decode_fail_signed_with_other_key(provider):
    other = JwtTokenProvider(secret_key="z" * 64)
    token, *_ = other.create_access_token(user_id=uuid.uuid4())

    with pytest.raises(UnauthorizedError):
        provider.decode_token(token=token)


def test_decode_fail_malformed_token(provider):
    with pytest.raises(UnauthorizedError):
        provider.decode_token(token="not-a-jwt")


def test_decode_fail_missing_jti(provider):

    token = jwt.encode(
        {"sub": str(uuid.uuid4()), "exp": 9999999999, "iat": 1},
        SECRET,
        algorithm="HS512",
    )

    with pytest.raises(UnauthorizedError):
        provider.decode_token(token=token)


# 생성(설정 검증) 성공 / 실패
# pytest 제공하는 기능 MonkeyPatch
def test_init_success_reads_secret_from_env(monkeypatch):
    monkeypatch.setenv("JWT_SECRET_KEY", SECRET)

    user_id = uuid.uuid4()
    token, *_ = JwtTokenProvider().create_access_token(user_id=user_id)

    assert (
        JwtTokenProvider(secret_key=SECRET).decode_token(token=token).user_id == user_id
    )


def test_init_fail_missing_secret_key(monkeypatch):
    # 다른 테스트가 .env 읽어 올 수 있으므로 환경변수를 지운다
    monkeypatch.delenv("JWT_SECRET_KEY", raising=False)

    with pytest.raises(RuntimeError):
        JwtTokenProvider()


def test_init_fail_short_secret_key():
    with pytest.raises(RuntimeError):
        JwtTokenProvider(secret_key="short")


def test_init_fail_unsupported_algorithm():
    with pytest.raises(RuntimeError):
        JwtTokenProvider(secret_key=SECRET, algorithm="none")
