# [담당3-영민] reservation_slots ORM 모델
# 도메인 TimeSlot 과 1:1 , 변환은 repositories._to_domain 

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
    
