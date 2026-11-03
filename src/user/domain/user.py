from dataclasses import dataclass
from enum import StrEnum
from datetime import datetime


class Role(StrEnum):
    CUSTOMER = "CUSTOMER"
    OWNER = "OWNER"


@dataclass
class User:
    id: int
    email: str
    password_hash: str
    name: str
    phone: str
    role: Role
    created_at: datetime
    updated_at: datetime | None = None
    deleted_at: datetime | None = None

    def is_active(self) -> bool:
        return self.deleted_at is None
