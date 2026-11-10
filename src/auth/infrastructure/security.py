import os
import uuid
from datetime import datetime, timedelta, UTC

import jwt

from auth.domain.provider import TokenProvider
from auth.domain.token_entities import TokenPayload
from common.errors import UnauthorizedError


class JwtTokenProvider(TokenProvider):
    def __init__(
        self,
        # HS512 스크릿 키
        secret_key: str | None = None,
        algorithm: str = "HS512",
        access_token_expire_minutes: int = 60,
    ):
        secret_key = secret_key or os.getenv("JWT_SECRET_KEY")
        self._validate_secret_key(secret_key)
        self._validate_algorithms(algorithm, secret_key)

        self.secret_key = secret_key
        self.algorithm = algorithm
        self.expire_minutes = access_token_expire_minutes

    def create_access_token(self, user_id: uuid.UUID) -> tuple[str, str, datetime, int]:
        now = datetime.now(UTC).replace(microsecond=0)
        expires_delta = timedelta(minutes=self.expire_minutes)
        expired_at = now + expires_delta
        expires_in = int(expires_delta.total_seconds())
        jti = str(uuid.uuid4())

        payload = {
            "sub": str(user_id),
            "jti": jti,
            "exp": expired_at,
            "iat": now,
        }

        encoded_jwt = jwt.encode(
            payload=payload, key=self.secret_key, algorithm=self.algorithm
        )
        return encoded_jwt, jti, expired_at, expires_in

    def decode_token(self, token: str) -> TokenPayload:
        try:
            payload = jwt.decode(
                token,
                self.secret_key,
                algorithms=[self.algorithm],
                options={
                    "require": ["sub", "jti", "exp", "iat"],
                    "verify_signature": True,
                    "verify_exp": True,
                    "verify_iat": True,
                },
            )

            # 서비스의 발급 형식: 시간 클레임은 정수 UNIX 초
            for claim in ("exp", "iat"):
                if type(payload[claim]) is not int:
                    raise ValueError(f"{claim} must be an integer timestamp")

            jti = payload["jti"]
            if not isinstance(jti, str) or not jti.strip():
                raise ValueError("jti must be a non-empty string")

            return TokenPayload(
                user_id=uuid.UUID(payload["sub"]),
                jti=jti,
                exp=datetime.fromtimestamp(payload["exp"], tz=UTC),
            )
        except (
            jwt.InvalidTokenError,
            KeyError,
            ValueError,
            TypeError,
            OverflowError,
            OSError,
        ) as e:
            raise UnauthorizedError("유효하지 않거나 만료된 토큰입니다.") from e

    def _validate_secret_key(self, secret_key: str | None) -> None:
        if not secret_key or not secret_key.strip():
            raise RuntimeError("JWT_SECRET_KEY 설정이 필요합니다.")

    def _validate_algorithms(self, algorithm: str, secret_key: str) -> None:
        if algorithm != "HS512":
            raise RuntimeError(f"지원하지 않는 JWT 알고리즘입니다: {algorithm}")

        if len(secret_key.encode("utf-8")) < 64:
            raise RuntimeError("HS512 시크릿은 최소 64바이트여야 합니다.")
