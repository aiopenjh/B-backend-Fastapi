"""식당 시드: CSV 한 줄 = 운영자 1명 + 식당 1개 + 메뉴 3개

실행 (프로젝트 루트에서, Docker DB가 켜져 있어야 함):
    uv run python src/restaurant/infrastructure/seed.py restaurants_menus_sample.csv

- 운영자 비밀번호는 모두 Seed1234! (담당 3 팀 시드 src/seed.py와 같음). bcrypt는 느려서 한 번만 계산해 재사용
- 음식 종류(cuisine)는 영어 코드: KOREAN, CHINESE, JAPANESE, WESTERN, BUNSIK, PUB, CAFE, WORLD
- 기존 시드 식당은 사진만 갱신. 운영자가 별도로 등록한 사진은 보존
- 빈 칸(image_url 등)은 NULL로 넣음
- 맨 끝에 한 번만 commit
"""

import argparse
import asyncio
import csv
import re
import sys
from pathlib import Path

# 이 파일을 직접 실행할 때도 src 안의 모듈(common, user, restaurant)을 찾을 수 있게 함
SRC_DIR = Path(__file__).resolve().parents[2]
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from restaurant.infrastructure.models import MenuModel, RestaurantModel
from user.domain.user import Role
from user.infrastructure.models import UserModel

DEMO_PASSWORD = "Seed1234!"  # 담당 3 팀 시드(src/seed.py)의 SEED_PASSWORD와 같게
MENU_COUNT = 3
PHOTO_PREFIX = "/static/restaurant-photos/"


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


async def refresh_sample_restaurant(session, user, owner, restaurant, menus):
    """목업 운영자 이메일과 고유 전화번호로 기존 식당을 찾아 ID와 예약을 유지한다."""
    match = re.fullmatch(r"owner(\d{5})@example\.com", owner["email"])
    if not match or owner["phone"] != f"010-2222-{int(match[1]):04d}" or user.role != Role.OWNER:
        raise ValueError("목업 전용 계정과 전화번호를 확인하세요.")
    existing = (await session.scalars(
        select(RestaurantModel).where(
            RestaurantModel.owner_id == user.id, RestaurantModel.phone == owner["phone"],
            RestaurantModel.deleted_at.is_(None),
        )
    )).one()
    if len(existing.menus) != len(menus):
        raise ValueError(f"식당 #{existing.id}의 메뉴 수가 목업과 다릅니다.")
    user.name = owner["name"]
    existing.name = restaurant["name"]
    existing.description = restaurant["description"]
    existing.address = restaurant["address"]
    existing.cuisine = restaurant["cuisine"]
    if not existing.image_url or existing.image_url.startswith((
        PHOTO_PREFIX, "https://commons.wikimedia.org/wiki/Special:FilePath/",
    )):
        existing.image_url = restaurant["image_url"]
    for current, new in zip(existing.menus, menus, strict=True):
        current.name = new["name"]
        current.price = new["price"]


async def seed_rows(session: AsyncSession, rows: list[dict], password_hash: str, *, refresh_sample: bool = False) -> int:
    """CSV 줄들을 DB에 넣음. 새로 넣은 식당 수를 돌려줌 (commit은 부른 쪽에서)"""
    added = 0
    for row in rows:
        owner, restaurant, menus = parse_row(row)

        existing_user = await session.scalar(
            select(UserModel).where(UserModel.email == owner["email"])
        )
        if existing_user is not None:
            if refresh_sample:
                await refresh_sample_restaurant(session, existing_user, owner, restaurant, menus)
                continue
            photo = restaurant["image_url"]
            if photo and photo.startswith(PHOTO_PREFIX):
                await session.execute(
                    update(RestaurantModel)
                    .where(
                        RestaurantModel.owner_id == existing_user.id,
                        RestaurantModel.name == restaurant["name"],
                        RestaurantModel.address == restaurant["address"],
                        RestaurantModel.deleted_at.is_(None),
                        RestaurantModel.image_url.is_distinct_from(photo),
                        or_(
                            RestaurantModel.image_url.is_(None),
                            RestaurantModel.image_url.startswith(PHOTO_PREFIX),
                            RestaurantModel.image_url.startswith(
                                "https://commons.wikimedia.org/wiki/Special:FilePath/"
                            ),
                        ),
                    )
                    .values(image_url=photo)
                    .execution_options(synchronize_session=False)
                )
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


async def main(rows: list[dict], *, refresh_sample: bool = False) -> None:
    # DB 연결은 실행할 때만 불러옴 (테스트에서 parse_row만 쓸 때는 필요 없음)
    from common.database import AsyncSessionLocal, engine
    from common.model import Base, init_models
    from user.infrastructure.security import BcryptPasswordHasher

    init_models()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)  # 테이블이 없으면 만듦

    password_hash = BcryptPasswordHasher().hash(DEMO_PASSWORD)  # 한 번만 계산

    async with AsyncSessionLocal() as session:
        added = await seed_rows(session, rows, password_hash, refresh_sample=refresh_sample)
        await session.commit()

    await engine.dispose()
    print(f"CSV {len(rows)}줄 중 새로 넣은 식당: {added}개 (나머지는 이미 있음)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("csv")
    parser.add_argument("--refresh-sample", action="store_true", help="기존 목업 식당과 메뉴를 CSV에 맞춰 갱신")
    args = parser.parse_args()
    asyncio.run(main(read_rows(args.csv), refresh_sample=args.refresh_sample))
