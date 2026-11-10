"""식당 시드: CSV 한 줄 = 운영자 1명 + 식당 1개 + 메뉴 3개

실행 (프로젝트 루트에서, Docker DB가 켜져 있어야 함):
    uv run python src/restaurant/infrastructure/seed.py restaurants_menus_sample.csv

- 운영자 비밀번호는 모두 Seed1234! (담당 3 팀 시드 src/seed.py와 같음). bcrypt는 느려서 한 번만 계산해 재사용
- 음식 종류(cuisine)는 영어 코드: KOREAN, CHINESE, JAPANESE, WESTERN, BUNSIK, PUB, CAFE, WORLD
- 이미 같은 이메일의 사용자가 있으면 그 줄은 건너뜀 (여러 번 실행해도 중복 없음)
- 빈 칸(image_url 등)은 NULL로 넣음
- 맨 끝에 한 번만 commit
"""

import asyncio
import csv
import sys
from pathlib import Path

# 이 파일을 직접 실행할 때도 src 안의 모듈(common, user, restaurant)을 찾을 수 있게 함
SRC_DIR = Path(__file__).resolve().parents[2]
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from restaurant.infrastructure.models import MenuModel, RestaurantModel
from user.domain.user import Role
from user.infrastructure.models import UserModel

DEMO_PASSWORD = "Seed1234!"  # 담당 3 팀 시드(src/seed.py)의 SEED_PASSWORD와 같게
MENU_COUNT = 3


def parse_row(row: dict) -> tuple[dict, dict, list[dict]]:
    """CSV 한 줄 -> (운영자, 식당, 메뉴 목록). DB 없이 테스트할 수 있게 dict로만 만듦"""
    owner = {
        "email": row["email"],
        "name": row["name"],
        "phone": row["phone"],
    }
    restaurant = {
        "name": row["name"],
        "description": row["description"] or None,
        "address": row["address"],
        "cuisine": row["cuisine"],
        "image_url": row["image_url"] or None,
        "phone": row["phone"] or None,
    }
    menus = []
    for i in range(1, MENU_COUNT + 1):
        menus.append({"name": row[f"menu{i}"], "price": int(row[f"menu{i}_price"])})
    return owner, restaurant, menus


async def seed_rows(session: AsyncSession, rows: list[dict], password_hash: str) -> int:
    """CSV 줄들을 DB에 넣음. 새로 넣은 식당 수를 돌려줌 (commit은 부른 쪽에서)"""
    added = 0
    for row in rows:
        owner, restaurant, menus = parse_row(row)

        # 같은 이메일의 운영자가 이미 있으면 건너뜀
        exists = await session.scalar(
            select(UserModel.id).where(UserModel.email == owner["email"])
        )
        if exists is not None:
            continue

        user = UserModel(
            email=owner["email"],
            name=owner["name"],
            phone=owner["phone"],
            password_hash=password_hash,
            role=Role.OWNER,
        )
        session.add(user)
        await session.flush()  # user.id를 받아 오기 위해

        session.add(
            RestaurantModel(
                owner_id=user.id,
                name=restaurant["name"],
                description=restaurant["description"],
                address=restaurant["address"],
                cuisine=restaurant["cuisine"],
                image_url=restaurant["image_url"],
                phone=restaurant["phone"],
                menus=[
                    MenuModel(name=menu["name"], price=menu["price"]) for menu in menus
                ],
            )
        )
        added += 1

    await session.flush()
    return added


def read_rows(csv_path: str) -> list[dict]:
    """CSV 파일 -> 줄 목록 (첫 줄은 열 이름)"""
    with open(csv_path, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


async def main(rows: list[dict]) -> None:
    # DB 연결은 실행할 때만 불러옴 (테스트에서 parse_row만 쓸 때는 필요 없음)
    from common.database import AsyncSessionLocal, engine
    from common.model import Base, init_models
    from user.infrastructure.security import BcryptPasswordHasher

    init_models()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)  # 테이블이 없으면 만듦

    password_hash = BcryptPasswordHasher().hash(DEMO_PASSWORD)  # 한 번만 계산

    async with AsyncSessionLocal() as session:
        added = await seed_rows(session, rows, password_hash)
        await session.commit()

    await engine.dispose()
    print(f"CSV {len(rows)}줄 중 새로 넣은 식당: {added}개 (나머지는 이미 있음)")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("사용법: uv run python src/restaurant/infrastructure/seed.py <csv 파일>")
        sys.exit(1)
    asyncio.run(main(read_rows(sys.argv[1])))
