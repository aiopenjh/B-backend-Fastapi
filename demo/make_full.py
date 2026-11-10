# [시연용] 식당 하나의 가장 가까운 예약 시간을 꽉 채운다 (마감 409 시연용) — 팀 코드(src/)는 고치지 않는다
"""실행 (저장소 맨 위 폴더에서, Docker DB가 켜져 있어야 함):

    uv run python demo/make_full.py "동네백반"

- 그 이름이 들어간 식당의, 지금 이후 아직 자리가 남은 가장 가까운 시간대 하나를 고른다
- 시연용 손님(demo.guest1@example.com …)들이 한 번에 최대 인원씩 예약해서 남은 자리를 0으로 만든다
  (한 사람은 같은 시간에 예약을 하나만 할 수 있어서 여러 명이 필요함)
- 시간대의 예약 인원과 실제 예약 합이 정확히 같게 넣는다 (취소해도 자리 계산이 맞음)
- 그다음 고객A로 그 시간을 누르면 409 SLOT_SOLD_OUT("방금 자리가 찼어요")
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))  # 팀 코드(src)를 import 할 수 있게

from sqlalchemy import select

from common.database import AsyncSessionLocal, engine
from common.model import init_models
from reservation.domain.reservation import ReservationStatus
from reservation.infrastructure.models import ReservationModel
from restaurant.infrastructure.models import RestaurantModel
from slot.domain.day_range import SEOUL, seoul_now
from slot.infrastructure.models import ReservationSlotModel
from user.domain.user import Role
from user.infrastructure.models import UserModel
from user.infrastructure.security import BcryptPasswordHasher


async def guest(session, number: int, password_hash: str) -> UserModel:
    """시연용 손님 하나 (없으면 만듦). 로그인할 일은 없어서 비밀번호는 쓰지 않음"""
    email = f"demo.guest{number}@example.com"
    user = await session.scalar(select(UserModel).where(UserModel.email == email))
    if user is None:
        user = UserModel(email=email, name=f"시연손님{number}", phone=f"010-9000-{number:04d}",
                         role=Role.CUSTOMER, password_hash=password_hash)
        session.add(user)
        await session.flush()
    return user


async def main(name: str) -> None:
    init_models()
    async with AsyncSessionLocal() as session:
        restaurant = await session.scalar(
            select(RestaurantModel)
            .where(RestaurantModel.name.contains(name), RestaurantModel.deleted_at.is_(None))
            .order_by(RestaurantModel.id)
        )
        if restaurant is None:
            print(f"'{name}' 식당이 없어요")
            return
        slot = await session.scalar(
            select(ReservationSlotModel)
            .where(
                ReservationSlotModel.restaurant_id == restaurant.id,
                ReservationSlotModel.starts_at > seoul_now(),
                ReservationSlotModel.reserved_guests < ReservationSlotModel.capacity,
            )
            .order_by(ReservationSlotModel.starts_at)
            .with_for_update()
        )
        if slot is None:
            print(f"{restaurant.name}: 자리가 남은 앞으로의 시간대가 없어요")
            return
        password_hash = BcryptPasswordHasher().hash(f"unused-{slot.id}!A1")
        number = 1
        while slot.reserved_guests < slot.capacity:
            user = await guest(session, number, password_hash)
            number += 1
            taken = await session.scalar(select(ReservationModel.id).where(
                ReservationModel.user_id == user.id, ReservationModel.slot_id == slot.id,
                ReservationModel.status == ReservationStatus.CONFIRMED.value,
            ))
            if taken:
                continue
            size = min(slot.max_party_size, slot.capacity - slot.reserved_guests)
            session.add(ReservationModel(user_id=user.id, slot_id=slot.id, party_size=size,
                                         contact_phone=user.phone, status=ReservationStatus.CONFIRMED.value))
            slot.reserved_guests += size
        await session.commit()
        when = slot.starts_at.astimezone(SEOUL).strftime("%Y-%m-%d %H:%M")
        print(f"{restaurant.name} {when} 시간대를 꽉 채웠어요 ({slot.reserved_guests}/{slot.capacity}석). "
              f"화면: /ui/restaurants/{restaurant.id}?date={when[:10]}")
    await engine.dispose()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print('사용법: uv run python demo/make_full.py "식당 이름"')
        sys.exit(1)
    asyncio.run(main(sys.argv[1]))
