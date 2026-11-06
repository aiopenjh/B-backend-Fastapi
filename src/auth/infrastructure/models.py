# [담당1 - 강성수]
import uuid
from datetime import datetime, UTC

from sqlalchemy import DateTime, String, BigInteger, Uuid, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from common.model import Base


class TokenBlackListModel(Base):
    __tablename__ = "token_blacklist"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    # UNIQUE가 인덱스를 함께 만들므로 index 필요없음
    token_jti: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    # cleanup_expired가 이 컬럼으로 범위 삭제하므로 인덱스
    expired_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
