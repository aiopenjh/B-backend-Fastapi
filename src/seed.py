# [담당3-영민] 시드 코드 작성 lifespan 에서 한 번. 회원 → 식당·메뉴 → 슬롯 → 예약 순서로 한 트랜잭션.
# 담당1, 담당2의 rows()를 기다리지 않고 한 파일에 모음

from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
# ▶ 팀 로거 — basicConfig 는 common.logger 가 이미 수행
from common.logger import get_logger     
from reservation.domain.reservation import ReservationStatus
from reservation.infrastructure.models import ReservationModel
from restaurant.infrastructure.models import MenuModel, RestaurantModel
from slot.domain.day_range import seoul_now
from slot.infrastructure.models import ReservationSlotModel
from user.domain.user import Role
from user.infrastructure.models import UserModel
from user.infrastructure.security import BcryptPasswordHasher

logger = get_logger(__name__)

SEED_PASSWORD = "Seed1234!"               # ▶ 시연용 공통 비밀번호 (8자 이상 · 영문/숫자/특수문자)
GUARD_EMAIL = "owner.a@example.com"       # ▶ 이 이메일이 있으면 시드가 이미 들어간 것 — 회원가입(#25)이 있어 users 행 수로는 판단 못 한다

# (email, name, phone, role)
USERS = [
    ("customer.a@example.com", "고객A", "010-1111-0001", Role.CUSTOMER),
    ("customer.b@example.com", "고객B", "010-1111-0002", Role.CUSTOMER),
    (GUARD_EMAIL,              "운영자A", "010-2222-0001", Role.OWNER),
    ("owner.b@example.com",    "운영자B", "010-2222-0002", Role.OWNER),
]

# (owner 인덱스 0=A·1=B, 식당 이름, 주소, cuisine, [(메뉴, 가격) × 3])
RESTAURANTS = [
    (0, "한옥집",     "서울 종로구 북촌로 11", "KOREAN",   [("김치찌개", 9000), ("제육볶음", 11000), ("계란말이", 7000)]),
    (0, "스시하루",   "서울 강남구 테헤란로 22", "JAPANESE", [("모둠초밥", 18000), ("연어덮밥", 14000), ("우동", 9000)]),
    (1, "트라토리아", "서울 마포구 와우산로 33", "ITALIAN",  [("까르보나라", 16000), ("마르게리타", 19000), ("티라미수", 8000)]),
]

# 식당마다 슬롯 4개: (시작 오프셋, capacity, max_party_size, [(고객 인덱스, party_size)…])
# reserved_guests 는 적지 않는다 — 아래 예약 party_size 합으로 계산해서 둘이 어긋날 수 없게 한다.
# 같은 고객·같은 슬롯 확정 예약은 하나만 (uq_reservations_user_slot_confirmed).
SLOTS = [
    (timedelta(hours=18),         10, 4, [(0, 2)]),          # 열린 슬롯 — 남은 자리 8 (API_SPEC '슬롯 7')
    (timedelta(hours=19),         10, 4, [(0, 4), (1, 4)]),  # 거의 찬 — 남은 자리 2 ('슬롯 9'), 3명 → SLOT_SOLD_OUT
    (timedelta(hours=20),          8, 4, [(0, 4), (1, 4)]),  # 꽉 찬 — 고객 2명 × 최대 4 = 8 이라 capacity 를 8 로
    (timedelta(days=1, hours=12),  8, 2, []),                # max_party_size 작은 슬롯 (모레 점심) — 3명 → PARTY_SIZE_EXCEEDED
]


async def seed(session: AsyncSession) -> None:
    """빈 DB 면 넣고, 시드 이메일이 이미 있으면 건너뜀 (재시작·--reload 에도 한 번만)."""
    if await session.scalar(select(UserModel.id).where(UserModel.email == GUARD_EMAIL)):
        logger.info("seed skipped — %s already exists", GUARD_EMAIL)   # ▶ 체크 8 '재시작해도 중복 없음' 을 로그로
        return

    # 1) 회원 4 — bcrypt 는 느리니 한 번만 해시해서 같이 활용
    password_hash = BcryptPasswordHasher().hash(SEED_PASSWORD)
    users = [
        UserModel(email=email, name=name, phone=phone, role=role, password_hash=password_hash)
        for email, name, phone, role in USERS
    ]
    customers = [u for u in users if u.role == Role.CUSTOMER]
    owners = [u for u in users if u.role == Role.OWNER]
    session.add_all(users)
    await session.flush()                 # ▶ id 발급 — 커밋은 마지막에 한 번 (중간 실패 시 전부 롤백)

    # 2) 식당 3 · 메뉴 9
    restaurants = []
    for owner_idx, name, address, cuisine, menus in RESTAURANTS:
        r = RestaurantModel(owner_id=owners[owner_idx].id, name=name, address=address, cuisine=cuisine)
        r.menus = [MenuModel(name=m, price=p) for m, p in menus]   # ▶ relationship 이라 restaurant_id 는 flush 때 채워진다
        restaurants.append(r)
    session.add_all(restaurants)
    await session.flush()

    # 3) 슬롯 12 — 시드를 넣는 날(서울) 기준 내일부터. 고정 날짜면 며칠 뒤 전부 '지난 슬롯'이 됨
    tomorrow = seoul_now().replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
    pending: list[tuple[ReservationSlotModel, list[tuple[int, int]]]] = []
    for r in restaurants:
        for offset, capacity, max_party, bookings in SLOTS:
            starts = tomorrow + offset
            slot = ReservationSlotModel(
                restaurant_id=r.id,
                starts_at=starts,
                ends_at=starts + timedelta(hours=1),   # [starts, ends) — 18-19 · 19-20 은 겹치지 않음
                capacity=capacity,
                reserved_guests=sum(size for _, size in bookings),   # ▶ 손으로 쓰지 않는다 — 예약 인원 합
                max_party_size=max_party,
            )
            pending.append((slot, bookings))
    session.add_all([s for s, _ in pending])
    await session.flush()                 # ▶ 슬롯 id 가 있어야 예약의 slot_id 를 채운다

    # 4) 예약 — 슬롯의 reserved_guests 와 정확히 같은 인원으로 (어긋나면 취소 시 release 가 500)
    reservations = [
        ReservationModel(
            user_id=customers[c].id,
            slot_id=slot.id,
            party_size=size,
            contact_phone=customers[c].phone,
            status=ReservationStatus.CONFIRMED.value,   # ▶ DB 에는 문자열 — CHECK (status IN ('CONFIRMED','CANCELLED'))
        )
        for slot, bookings in pending
        for c, size in bookings
    ]
    session.add_all(reservations)
    await session.commit()                # ▶ 한 번. 시드 전체가 원자적

    logger.info(
        "seeded: users=%d restaurants=%d menus=%d slots=%d reservations=%d",
        len(users), len(restaurants), sum(len(m) for *_, m in RESTAURANTS), len(pending), len(reservations),
    )                                     # ▶ 체크 8 '시드 주입 로그'