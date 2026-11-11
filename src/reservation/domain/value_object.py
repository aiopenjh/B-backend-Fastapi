# [담당 4] 예약 값 객체 : 연락처(휴대폰 번호) 규칙, 예약 쪽에서 본 행동하는 사람(Actor). API든 화면이든 어디로 들어와도 같은 검사와 모양을 쓴다
import re
import uuid
from dataclasses import dataclass
from enum import StrEnum

from common.errors import InvalidInputError

# 010은 가운데가 항상 4자리, 옛 번호(011·016~019)는 3~4자리. \d 대신 [0-9]로 아라비아 숫자만 받는다
PHONE_REGEX = re.compile(r"(?:010-?[0-9]{4}|01[16789]-?[0-9]{3,4})-?[0-9]{4}")


@dataclass(frozen=True)
class ContactPhone:
    """휴대폰 번호. 하이픈은 있어도 없어도 받고, 010-1234-5678 모양으로 맞춰 둔다."""

    value: str

    def __post_init__(self) -> None:
        # 글자가 아니면(숫자 등) 모양을 볼 것도 없이 막는다
        raw = self.value.strip() if isinstance(self.value, str) else ""
        # fullmatch라서 앞뒤에 다른 글자가 붙으면 통과하지 못한다
        if not PHONE_REGEX.fullmatch(raw):
            raise InvalidInputError(
                errors={"contact_phone": ["휴대폰 번호 형식이 아닙니다."]}
            )
        digits = raw.replace("-", "")
        # frozen이라 self.value = 대입이 막혀 있어 object.__setattr__로 바꾼다 (담당 1 Email과 같은 방식)
        object.__setattr__(self, "value", f"{digits[:3]}-{digits[3:-4]}-{digits[-4:]}")


class ActorRole(StrEnum):
    """예약 쪽에서 쓰는 역할. 로그인 쪽 AuthRole과 글자가 같아서 그대로 바꿔 끼울 수 있다."""

    CUSTOMER = "CUSTOMER"
    OWNER = "OWNER"
    ADMIN = "ADMIN"


@dataclass(frozen=True)
class Actor:
    """예약을 만들고·취소하고·입장 확인하는 사람 (예약 쪽 값 객체).
    예약 도메인이 로그인 쪽 AuthenticatedUser를 직접 모르도록, 입구(라우터·응답 스키마)에서
    Actor(user.user_id, user.role)로 바꿔 넘긴다."""

    user_id: uuid.UUID
    role: ActorRole

    def __post_init__(self) -> None:
        # 글자("OWNER")나 다른 Enum(AuthRole.OWNER)으로 와도 ActorRole로 맞춘다. 모르는 역할이면 ValueError
        # (역할은 손님 입력이 아니라 로그인 토큰에서 나온 값이라, 틀리면 422가 아니라 코드 버그다)
        object.__setattr__(self, "role", ActorRole(self.role))

    def is_owner(self) -> bool:
        return self.role is ActorRole.OWNER

    def is_admin(self) -> bool:
        return self.role is ActorRole.ADMIN
