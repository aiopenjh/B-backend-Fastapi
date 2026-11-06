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


def init_models() -> None:
    """SQLAlchemy 모델 메타데이터 등록"""
    """모델을 import해서 등록만 함 None: 추가"""
    import user.infrastructure.models  # 회원 [담당1-강성수]
    import reservation.infrastructure.models # 예약 [담당4-김민지]
    import slot.infrastructure.models # 슬롯[담당3-이영민]
    import restaurant.infrastructure.models # 식당 [담당2-김태양]
    """순환 import 방지를 위해 함수 안에서 import"""
