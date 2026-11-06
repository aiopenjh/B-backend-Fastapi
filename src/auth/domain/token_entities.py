import uuid

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class TokenPayload:
    user_id: uuid.UUID
    jti: str
    exp: datetime


@dataclass
class BlackListToken:
    jti: str
    expired_at: datetime
