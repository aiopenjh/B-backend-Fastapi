import uuid

from abc import ABC, abstractmethod
from datetime import datetime
from auth.domain.token_entities import TokenPayload


class TokenProvider(ABC):
    @abstractmethod
    def create_access_token(self, user_id: uuid.UUID) -> tuple[str, str, datetime, int]:
        """(token, jti, expired_at, expires_in_seconds) 반환"""
        pass

    @abstractmethod
    def decode_token(self, token: str) -> TokenPayload:
        """토큰 검증 및 페이로드 추출"""
        pass
