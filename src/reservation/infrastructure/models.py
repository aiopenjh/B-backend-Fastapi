# [담당 4] 예약 창고 : reservations 테이블 정의
import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Uuid,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from common.model import Base


class ReservationModel(Base):
    """reservations 표 한 줄의 모양 (DB 전용). 도메인 Reservation으로 바꾸는 건 repositories.py의 to_reservation."""

    __tablename__ = "reservations"

    # DB가 지키는 마지막 규칙 : 인원은 1명 이상, 상태는 두 값만, 확정 예약은 사람·슬롯당 하나 (코드에서 실수해도 DB가 막음)
    __table_args__ = (
        CheckConstraint("party_size >= 1", name="ck_reservations_party_size_positive"),
        CheckConstraint(
            "status IN ('CONFIRMED', 'CANCELLED')", name="ck_reservations_status"
        ),
        # 취소된 예약은 여러 개여도 되니까, 확정(CONFIRMED)인 줄만 겹치지 않게 막는다 (부분 unique 인덱스)
        Index(
            "uq_reservations_user_slot_confirmed",
            "user_id",
            "slot_id",
            unique=True,
            postgresql_where=text("status = 'CONFIRMED'"),
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id"), nullable=False, index=True
    )

    slot_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("reservation_slots.id"), nullable=False, index=True
    )

    party_size: Mapped[int] = mapped_column(Integer, nullable=False)

    contact_phone: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # DB에는 문자열로 저장. 꺼낼 때 ReservationStatus로 바꾼다.(to_reservation)
    status: Mapped[str] = mapped_column(String(16), nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    # 도메인에는 없는 칸. 행이 바뀔 때마다 DB가 알아서 시각을 갱신한다.
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    cancelled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # 누가·왜 취소했나 (CancelledBy, CancelReason을 문자열로 저장). 취소 전에는 비어 있다.
    cancelled_by: Mapped[str | None] = mapped_column(String(16), nullable=True)
    cancel_reason: Mapped[str | None] = mapped_column(String(32), nullable=True)
    cancel_note: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # 운영자가 "입장"을 누른 시각. 비어 있으면 아직 안 온 것 (노쇼 판단에 씀)
    checked_in_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
