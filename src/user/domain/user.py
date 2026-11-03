import re
import uuid

from dataclasses import dataclass
from enum import StrEnum
from datetime import datetime, UTC
from common.errors import InvalidInputError
from user.domain.exceptions import InvalidOldPasswordError, SamePasswordError
from user.domain.hasher import PasswordHasher

EMAIL_REGEX = re.compile(r"^[\w\.-]+@[\w\.-]+\.\w+$")
PASSWORD_REGEX = re.compile(
    r"^(?=.*[A-Za-z])(?=.*\d)(?=.*[@$!%*#?&])[A-Za-z\d@$!%*#?&]{8,}$"
)


class Role(StrEnum):
    CUSTOMER = "CUSTOMER"
    OWNER = "OWNER"


@dataclass
class User:
    email: str
    password_hash: str
    name: str
    phone: str
    created_at: datetime

    role: Role
    id: uuid.UUID | None = None
    updated_at: datetime | None = None
    deleted_at: datetime | None = None

    def __post_init__(self):
        self._validate_email(self.email)
        self._validate_name(self.name)

    @classmethod
    def create(
        cls,
        email: str,
        raw_password: str,
        name: str,
        phone: str,
        hasher: PasswordHasher,
        role: Role = Role.CUSTOMER,
    ) -> "User":
        cls._validate_password(raw_password)
        password_hash = hasher.hash(raw_password)

        return cls(
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
            raise InvalidOldPasswordError(
                message="기존 비밀번호가 일치하지 않습니다.",
            )

        if old_password == new_password:
            raise SamePasswordError(
                message="새 비밀번호는 이전 비밀번호와 동일할 수 없습니다.",
            )

        self._validate_password(new_password)

        self.password_hash = hasher.hash(new_password)
        self.updated_at = datetime.now(UTC)

    @staticmethod
    def _validate_email(email: str) -> None:
        if not EMAIL_REGEX.match(email):
            raise InvalidInputError(
                errors={"email": ["올바른 이메일 형식이 아닙니다."]}
            )

    @staticmethod
    def _validate_name(name: str) -> None:
        if not (2 <= len(name) <= 20):
            raise InvalidInputError(
                errors={"name": ["이름 길이는 2자 이상 20자 이하여야 합니다"]}
            )

    @staticmethod
    def _validate_password(raw_password: str) -> None:
        if not PASSWORD_REGEX.match(raw_password):
            raise InvalidInputError(
                errors={
                    "password": [
                        "비밀번호는 8자 이상이어야 하며 영문, 숫자, 특수문자를 포함해야 합니다."
                    ]
                }
            )
