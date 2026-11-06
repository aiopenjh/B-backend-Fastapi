# [담당1 - 강성수]

import uuid

from sqlalchemy import Uuid, String
from sqlalchemy.orm import Mapped, mapped_column

from common.model import Base, DateTimeBase
from user.domain.user import User, Role
from user.domain.value_object import Email


class UserModel(Base, DateTimeBase):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    email: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    phone: Mapped[str] = mapped_column(String(20), nullable=False)
    role: Mapped[str] = mapped_column(String(20), default=Role.CUSTOMER, nullable=False)

    def to_user(self) -> User:
        """ORM Model -> Domain Entity 반환"""
        return User(
            id=self.id,
            email=Email(self.email),
            name=self.name,
            password_hash=self.password_hash,
            phone=self.phone,
            role=Role(self.role),
            created_at=self.created_at,
            updated_at=self.updated_at,
            deleted_at=self.deleted_at,
        )
