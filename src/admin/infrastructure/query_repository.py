#[담당 5] 관리자 창고 : 운영자 목록 + 식당 수, 식당 예약 + 예약자 꺼내기 (읽기 전용)
import uuid
from dataclasses import dataclass
from datetime import date

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from reservation.domain.reservation import Reservation  # 담당 4: 예약
from reservation.infrastructure.models import ReservationModel  # 담당 4: 예약 표(DB)
from reservation.infrastructure.repositories import to_reservation  # 담당 4: 표 → 예약
from restaurant.infrastructure.models import RestaurantModel  # 담당 2 식당표(DB)
from slot.domain.day_range import seoul_day_range  # 담당 3: 서울 기준 하루 범위
from slot.domain.time_slot import TimeSlot  # 담당 3: 슬롯
from slot.infrastructure.models import ReservationSlotModel  # 담당 3: 슬롯 표(DB)
from slot.infrastructure.repositories import _to_domain  # 담당 3: 표 → 슬롯
from user.domain.user import User  # 담당1 회원
from user.infrastructure.models import UserModel  # 담당 1: 회원 표 (DB)


@dataclass(frozen=True)
class Guest:
    """예약자 정보: 화면에 보여 줄 칸만 (비밀번호 칸은 꺼내지 않음)"""

    name: str
    email: str
    phone: str


class AdminQueryRepository:
    def __init__(self, db:AsyncSession):
        self.db = db

    async def list_owners(self, offset: int, limit: int) -> tuple[list[tuple[User, int]], int]:
        #운영자만, 탈퇴한 사람 빼기
        conditions = [UserModel.role == "OWNER", UserModel.deleted_at.is_(None)]
        total = await self.db.scalar(select(func.count()).select_from(UserModel).where(*conditions))

        # 식당 수 세기: 식당이 없어도 운영자는 남기기(outerjoin) -> 0개
        restaurant_count = func.count(RestaurantModel.id)
        rows = await self.db.execute(
            select(UserModel, restaurant_count)
            .outerjoin(RestaurantModel, and_(RestaurantModel.owner_id == UserModel.id, RestaurantModel.deleted_at.is_(None)))
            .where(*conditions)
            .group_by(UserModel.id)
            .order_by(UserModel.created_at, UserModel.id)  # 가입 순, 같으면 번호 순 (페이지가 겹치지 않게)
            .offset(offset)
            .limit(limit)
        )
        return [(m.to_user(), count) for m, count in rows], total or 0

    async def get_owner(self, owner_id: uuid.UUID) -> User | None:
        """운영자 한 명. 없거나 운영자가 아니거나 탈퇴했으면 None → 매니저가 404"""
        model = await self.db.scalar(
            select(UserModel).where(
                UserModel.id == owner_id, UserModel.role == "OWNER", UserModel.deleted_at.is_(None)
            )
        )
        return model.to_user() if model else None

    async def list_reservations(
        self, restaurant_id: int, day: date | None, offset: int, limit: int
    ) -> tuple[list[tuple[Reservation, TimeSlot, Guest]], int]:
        """식당 예약 목록 + 예약자 이름·이메일·연락처 (운영자 창고와 같은 순서, users 표를 하나 더 이음)"""
        conditions = [ReservationSlotModel.restaurant_id == restaurant_id]
        if day is not None:
            start, end = seoul_day_range(day)
            conditions += [ReservationSlotModel.starts_at >= start, ReservationSlotModel.starts_at < end]

        total = await self.db.scalar(
            select(func.count())
            .select_from(ReservationModel)
            .join(ReservationSlotModel, ReservationSlotModel.id == ReservationModel.slot_id)
            .where(*conditions)
        )
        # 예약 → 슬롯(식당·날짜) → 회원(예약자). 회원 표는 이름·이메일·전화 칸만 꺼냄
        rows = await self.db.execute(
            select(ReservationModel, ReservationSlotModel, UserModel.name, UserModel.email, UserModel.phone)
            .join(ReservationSlotModel, ReservationSlotModel.id == ReservationModel.slot_id)
            .join(UserModel, UserModel.id == ReservationModel.user_id)
            .where(*conditions)
            .order_by(ReservationSlotModel.starts_at, ReservationModel.id)  # 이용 시작 시각 순
            .offset(offset)
            .limit(limit)
        )
        return [
            (to_reservation(r), _to_domain(s), Guest(name=name, email=email, phone=phone))
            for r, s, name, email, phone in rows
        ], total or 0
