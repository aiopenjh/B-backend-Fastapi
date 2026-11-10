import uuid

from dataclasses import dataclass
from datetime import datetime, timedelta

# 만료된 블랙리스트 행을 지울 때 두는 여유 시간.
# 서버가 여러 대이고 시계가 조금씩 다르면, 한 서버 기준으로 막 만료된 토큰이
# 다른 서버에서는 아직 유효할 수 있다. 그 행을 지우면 로그아웃한 토큰이 다시 통한다
BLACKLIST_PURGE_GRACE = timedelta(minutes=5)


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
