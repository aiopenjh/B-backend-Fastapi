from datetime import datetime, UTC

from sqlalchemy import DateTime
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class DateTimeBase:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )

    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        default=None,
        onupdate=lambda: datetime.now(UTC),
        nullable=True,
    )

    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None, nullable=True
    )


def init_models():
    """SQLAlchemy 모델 메타데이터 등록"""
    import user.infrastructure.models  # 회원 [담당1-강성수]
