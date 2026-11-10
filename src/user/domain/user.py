# [담당1 - 강성수]
import re
import string
import uuid

from dataclasses import dataclass
from enum import StrEnum
from datetime import datetime, UTC

from user.domain.exceptions import (
    InvalidOldPasswordError,
    InvalidRoleChangeError,
    SamePasswordError,
)
from user.domain.hasher import PasswordHasher
from user.domain.value_object import Email

from common.errors import InvalidInputError

# 72는 bcrypt 입력 한도(바이트). 허용 문자를 ASCII로만 두어 글자 수 = 바이트 수가 되게 한다.
# 특수문자는 공백을 뺀 ASCII 키보드 기호 전부를 받는다 (비밀번호 관리자가 만드는 . _ - 등).
# 숫자는 \d가 아니라 0-9로 적는다 (\d는 전각·아랍 숫자도 받음)
PASSWORD_MAX_LENGTH = 72
PASSWORD_SYMBOLS = re.escape(string.punctuation)
PASSWORD_REGEX = re.compile(
    rf"(?=.*[A-Za-z])(?=.*[0-9])(?=.*[{PASSWORD_SYMBOLS}])"
    rf"[A-Za-z0-9{PASSWORD_SYMBOLS}]{{8,{PASSWORD_MAX_LENGTH}}}"
)
PASSWORD_ERROR_MESSAGE = (
    "비밀번호는 8자 이상 72자 이하이며 영문, 숫자, 특수문자를 하나 이상 포함해야 합니다. "
    "특수문자는 영문 자판의 기호(공백 제외, 예: . _ - ! @ #)를 쓸 수 있습니다."
)


class Role(StrEnum):
    CUSTOMER = "CUSTOMER"
    OWNER = "OWNER"
    ADMIN = "ADMIN"


ASSIGNABLE_ROLES = frozenset({Role.CUSTOMER, Role.OWNER})


@dataclass
class User:
    email: Email
    password_hash: str
    name: str
    phone: str
    created_at: datetime

    role: Role
    id: uuid.UUID | None = None
    updated_at: datetime | None = None
    deleted_at: datetime | None = None

    def __post_init__(self):
        self._validate_name(self.name)

    @classmethod
    def create(
        cls,
        email: Email,
        raw_password: str,
        name: str,
        phone: str,
        hasher: PasswordHasher,
        role: Role = Role.CUSTOMER,
    ) -> "User":
        cls._validate_password(raw_password)
        password_hash = hasher.hash(raw_password)

        return cls(
            id=uuid.uuid4(),
            email=email,
            name=name,
            password_hash=password_hash,
            phone=phone,
            role=role,
            created_at=datetime.now(UTC),
        )

    def is_active(self) -> bool:
        return self.deleted_at is None

    def change_password(
        self,
        old_password: str,
        new_password: str,
        hasher: PasswordHasher,
    ) -> None:
        """비밀번호 변경"""
        if not hasher.verify(old_password, self.password_hash):
            raise InvalidOldPasswordError()

        if old_password == new_password:
            raise SamePasswordError()

        self._validate_password(new_password)

        self.password_hash = hasher.hash(new_password)
        self.updated_at = datetime.now(UTC)

    def change_owner_role(self, new_role: Role | str) -> None:
        """관리자가 CUSTOMER <-> OWNER 사이에서 역할을 바꾼다"""
        # 문자열이 들어와도 Role로 바꿔 저장한다. 그대로 두면 저장할 때 .value에서 깨진다
        try:
            role = Role(new_role)
        except ValueError:
            raise InvalidRoleChangeError()

        if self.role == Role.ADMIN or role not in ASSIGNABLE_ROLES:
            raise InvalidRoleChangeError()

        if self.role == role:
            return

        self.role = role
        self.updated_at = datetime.now(UTC)

    @staticmethod
    def _validate_name(name: str) -> None:
        if not (2 <= len(name) <= 20):
            raise InvalidInputError(
                errors={"name": ["이름 길이는 2자 이상 20자 이하여야 합니다"]}
            )

    @staticmethod
    def _validate_password(raw_password: str) -> None:
        # fullmatch: match + "$"는 끝의 "\n"을 통과시켜 줄바꿈까지 해시에 들어간다
        if not PASSWORD_REGEX.fullmatch(raw_password):
            raise InvalidInputError(errors={"password": [PASSWORD_ERROR_MESSAGE]})
