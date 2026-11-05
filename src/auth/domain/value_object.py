import uuid
from enum import StrEnum
from dataclasses import dataclass


class AuthRole(StrEnum):
    OWNER = "OWNER"
    CUSTOMER = "CUSTOMER"


@dataclass(frozen=True)
class AuthenticatedUser:
    user_id: uuid.UUID
    role: AuthRole

    def is_owner(self) -> bool:
        return self.role == AuthRole.OWNER

    def is_customer(self) -> bool:
        return self.role == AuthRole.CUSTOMER
