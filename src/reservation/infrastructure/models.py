# [담당 4] 예약 창고 : reservations 테이블 정의
import uuid
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import Uuid, BigInteger, CheckConstraint, DateTime, ForeignKey, Integer, String, func
from datetime import datetime

from common.model import Base


class ReservationModel(Base):
    __tablename__ = "reservations"

    __table_args__ = (
        CheckConstraint("party_size >= 1", name="ck_reservations_party_size_positive"),
        CheckConstraint("status IN ('CONFIRMED', 'CANCELLED')", name="ck_reservations_status")
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"), nullable=False, index=True)

    slot_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("reservation_slots.id"), nullable=False, index=True)

    party_size: Mapped[int] = mapped_column(Integer, nullable=False)

    contact_phone: Mapped[str | None] = mapped_column(String(20), nullable=True)

    status: Mapped[str] = mapped_column(String(16), nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
