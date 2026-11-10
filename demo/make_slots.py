# [시연용] 모든 식당에 앞으로 며칠치 예약 시간대를 채운다 — 팀 코드(src/)는 고치지 않는다
"""실행 (저장소 맨 위 폴더에서, Docker DB가 켜져 있어야 함):

    uv run python demo/make_slots.py          # 내일부터 14일치
    uv run python demo/make_slots.py 30       # 내일부터 30일치

- 식당마다 하루 3번: 12:00 · 18:00 · 19:30 (서울 시각, 한 번에 90분)
- 그날 이미 시간대가 있는 식당은 그날을 건너뜀 (시드 시간대와 겹치지 않게, 여러 번 돌려도 중복 없음)
- 정원·최대 인원은 식당 번호로 정해서 식당마다 조금씩 다름 (작은 곳 12석·최대 4명 ~ 큰 곳 24석·최대 6명)
- 맨 끝에 한 번만 commit
"""

import asyncio
import sys
from datetime import datetime, time, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))  # 팀 코드(src)를 import 할 수 있게

from sqlalchemy import func, select

from common.database import AsyncSessionLocal, engine
from common.model import init_models
from restaurant.infrastructure.models import RestaurantModel
from slot.domain.day_range import SEOUL, seoul_now
from slot.infrastructure.models import ReservationSlotModel

TIMES = [time(12, 0), time(18, 0), time(19, 30)]
LENGTH = timedelta(minutes=90)
SIZES = [(12, 4), (16, 4), (20, 6), (24, 6)]  # (정원, 한 번에 최대 인원) — 식당 번호로 하나 고름


async def main(days: int) -> None:
    init_models()
    tomorrow = seoul_now().date() + timedelta(days=1)
    added = 0
    async with AsyncSessionLocal() as session:
        restaurant_ids = list(await session.scalars(
            select(RestaurantModel.id).where(RestaurantModel.deleted_at.is_(None)).order_by(RestaurantModel.id)
        ))
        # 이미 시간대가 있는 (식당, 서울 날짜) 짝 — 그날은 건너뜀
        seoul_day = func.date(func.timezone("Asia/Seoul", ReservationSlotModel.starts_at))
        taken = {
            (rid, day) for rid, day in await session.execute(
                select(ReservationSlotModel.restaurant_id, seoul_day).group_by(ReservationSlotModel.restaurant_id, seoul_day)
            )
        }
        for rid in restaurant_ids:
            capacity, max_party = SIZES[rid % len(SIZES)]
            for n in range(days):
                day = tomorrow + timedelta(days=n)
                if (rid, day) in taken:
                    continue
                for at in TIMES:
                    starts = datetime.combine(day, at, tzinfo=SEOUL)
                    session.add(ReservationSlotModel(
                        restaurant_id=rid, starts_at=starts, ends_at=starts + LENGTH,
                        capacity=capacity, reserved_guests=0, max_party_size=max_party,
                    ))
                    added += 1
        await session.commit()
    await engine.dispose()
    print(f"식당 {len(restaurant_ids)}곳, {tomorrow}부터 {days}일치 → 새 시간대 {added}개")


if __name__ == "__main__":
    asyncio.run(main(int(sys.argv[1]) if len(sys.argv) > 1 else 14))
