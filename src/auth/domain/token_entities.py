import uuid

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class TokenPayload:
    user_id: uuid.UUID
    jti: str
    exp: datetime


@dataclass(frozen=True)
class BlackListToken:
    jti: str
    user_id: uuid.UUID
    expired_at: datetime
