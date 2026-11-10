# [담당3-영민] reservation_slots ORM 모델
# 도메인 TimeSlot에 대응하는 ORM 모델, 변환은 repositories._to_domain 

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from common.model import Base


class ReservationSlotModel(Base):
    __tablename__ = "reservation_slots"
    __table_args__ = (
        CheckConstraint("reserved_guests >= 0 AND reserved_guests <= capacity",
            name="ck_reservation_slots_reserved_guests_range"),
        CheckConstraint("max_party_size >= 1", name="ck_reservation_slots_max_party_size"),
        CheckConstraint("starts_at < ends_at", name="ck_reservation_slots_time_order"),
        Index("ix_reservation_slots_restaurant_starts", "restaurant_id", "starts_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    restaurant_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("restaurants.id"), nullable=False, index=True
    )
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    capacity: Mapped[int] = mapped_column(Integer, nullable=False)
    reserved_guests: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    max_party_size: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )



    
