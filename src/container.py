import asyncio
import os
from datetime import datetime, timedelta
from functools import lru_cache
from typing import Annotated

from fastapi import Depends, FastAPI
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from common.database import get_session  # 공통: 요청마다 DB 연결 하나
from common.logger import get_logger  # 공통: 로그
from slot.domain.day_range import seoul_now  # 담당 3: 지금 시각 (서울)

logger = get_logger(__name__)

from auth.application.service import AuthService, make_dummy_hash
from auth.domain.limiter import LoginAttemptLimiter
from auth.domain.provider import TokenProvider
from auth.domain.repository import TokenBlackListRepository
from auth.infrastructure.login_limiter import InMemoryLoginAttemptLimiter
from auth.infrastructure.repositories import SQLAlchemyTokenBlackListRepository
from auth.infrastructure.security import JwtTokenProvider
from auth.presentation.dependencies import auth_service

from admin.application.service import AdminService  # 담당 5: 관리자 매니저
from browse.application.service import BrowseService  # 담당 5: 손님 둘러보기 매니저
from owner.application.service import OwnerService  # 담당 5: 운영자 매니저

from slot.application.service import SlotService  # 담당 3: 슬롯(예약 시간대) 매니저
from slot.domain.repository import SlotRepository  # 담당 3: 슬롯 창고 약속
from slot.infrastructure.repositories import (
    SQLAlchemySlotRepository,
)  # 담당 3: 슬롯 창고

from reservation.application.query_service import (
    ReservationQueryService,
)  # 담당 5: 예약 조회 매니저
from reservation.application.service import ReservationService  # 담당 4 : 예약 매니저
from reservation.infrastructure.repositories import (
    SQLAlchemyReservationRepository,
)  # 담당 4 : 예약 창고

from restaurant.application.service import RestaurantService  # 담당 2: 식당 매니저
from restaurant.infrastructure.repository import (
    RestaurantRepository,
)  # 담당 2: 식당 창고

from user.application.service import UserService  # 담당 1: 회원 매니저
from common.unit_of_work import UnitOfWork  # 담당 1: 변경 확정 약속
from user.domain.hasher import PasswordHasher  # 담당 1: 비밀번호 암호화 약속
from user.domain.repository import UserRepository  # 담당 1: 회원 창고 약속
from user.infrastructure.repositories import (
    SQLAlchemyUserRepository,
)  # 담당 1: 회원 창고
from user.infrastructure.security import BcryptPasswordHasher  # 담당 1: 비밀번호 암호화
from user.infrastructure.unit_of_work import SQLAlchemyUnitOfWork  # 담당 1: 변경 확정
from user.presentation.dependencies import user_service

password_hasher: PasswordHasher = BcryptPasswordHasher()
# 담당 1: 로그인 실패 횟수 (모든 요청이 하나를 같이 써야 횟수가 쌓인다)
login_limiter: LoginAttemptLimiter = InMemoryLoginAttemptLimiter()
# 담당 1: 없는 계정도 같은 시간이 걸리게 검증할 더미 해시 (시작할 때 한 번, 약 0.25초)
dummy_password_hash: str = make_dummy_hash(password_hasher)


# 담당 1: 회원 창고 공장
def create_user_repository(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> UserRepository:
    return SQLAlchemyUserRepository(session=session)


# 담당 1: 변경 확정(UoW) 공장
def create_unit_of_work(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> UnitOfWork:
    return SQLAlchemyUnitOfWork(session=session)


# 담당 1: 회원 매니저 공장
def create_user_service(
    repo: Annotated[UserRepository, Depends(create_user_repository)],
    uow: Annotated[UnitOfWork, Depends(create_unit_of_work)],
) -> UserService:
    return UserService(
        repo=repo,
        uow=uow,
        hasher=password_hasher,
    )


# 담당 1: 토큰 발급기 (처음 쓸 때 한 번만 만든다)
@lru_cache
def get_token_provider() -> TokenProvider:
    return JwtTokenProvider()


def create_token_blacklist_repository(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> TokenBlackListRepository:
    return SQLAlchemyTokenBlackListRepository(session=session)


def create_auth_service(
    request: Request,
    user_repo: Annotated[UserRepository, Depends(create_user_repository)],
    blacklist_repo: Annotated[
        TokenBlackListRepository, Depends(create_token_blacklist_repository)
    ],
    token_provider: Annotated[TokenProvider, Depends(get_token_provider)],
    uow: Annotated[UnitOfWork, Depends(create_unit_of_work)],
) -> AuthService:
    return AuthService(
        user_repo=user_repo,
        hasher=password_hasher,
        blacklist_repo=blacklist_repo,
        token_provider=token_provider,
        uow=uow,
        login_limiter=login_limiter,
        # 프록시 뒤라면 uvicorn --forwarded-allow-ips를 설정해야 실제 접속 IP가 들어온다
        client_ip=request.client.host if request.client else None,
        dummy_hash=dummy_password_hash,
    )


# 담당 3: 슬롯 창고 공장 (예약 공장도 이것을 받는다 — 같은 요청이면 같은 세션)
def create_slot_repository(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> SlotRepository:
    return SQLAlchemySlotRepository(session)


# 담당 3: 슬롯 매니저 공장
def create_slot_service(
    repo: Annotated[SlotRepository, Depends(create_slot_repository)],
) -> SlotService:
    return SlotService(repo)


# 담당 5: 운영자 매니저 공장
def create_owner_service(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> OwnerService:
    return OwnerService(session)


# 담당 5: 관리자 매니저 공장
def create_admin_service(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> AdminService:
    return AdminService(session)


# 담당 5: 손님 둘러보기 매니저 공장
def create_browse_service(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> BrowseService:
    return BrowseService(session)


# 담당 5: 예약 조회 매니저 공장
def create_reservation_query_service(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ReservationQueryService:
    return ReservationQueryService(session)


# 담당 2: 식당 매니저 공장
def create_restaurant_service(
    session: Annotated[AsyncSession, Depends(get_session)],
    uow: Annotated[UnitOfWork, Depends(create_unit_of_work)],
) -> RestaurantService:
    return RestaurantService(repo=RestaurantRepository(session), uow=uow)


# 담당 4 : 노쇼 유예 시간 (시작 후 이만큼 지나야 노쇼). 환경변수 NO_SHOW_GRACE_SECONDS(초), 기본 15분
def env_seconds(name: str, default: int) -> int:
    """환경변수에서 초(정수)를 읽는다. 비었거나 숫자가 아니거나 음수면 기본값을 쓰고, 잘못된 값은 경고 로그를 남긴다 (앱이 켜지다 죽지 않게)"""
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        value = int(raw)
    except ValueError:
        logger.warning(
            "%s=%r 은(는) 숫자가 아니라 기본값 %d초를 씁니다", name, raw, default
        )
        return default
    if value < 0:
        logger.warning("%s=%d 은(는) 음수라 기본값 %d초를 씁니다", name, value, default)
        return default
    return value


NO_SHOW_GRACE = timedelta(seconds=env_seconds("NO_SHOW_GRACE_SECONDS", 900))


# 담당 4 : 예약 매니저 공장 (생성, 취소, 노쇼, 입장 확인)
def create_reservation_service(
    session: Annotated[AsyncSession, Depends(get_session)],
    slot_repo: Annotated[SlotRepository, Depends(create_slot_repository)],
    uow: Annotated[UnitOfWork, Depends(create_unit_of_work)],
) -> ReservationService:
    return ReservationService(
        reservation_repo=SQLAlchemyReservationRepository(session),
        slot_repo=slot_repo,
        uow=uow,
        no_show_grace=NO_SHOW_GRACE,
    )


# 담당 4 : 자동 노쇼 한 번. 새 세션으로 예약 매니저를 위 공장과 똑같이 조립해서 노쇼 대상을 처리한다
async def expire_no_shows_once(
    session_factory: async_sessionmaker[AsyncSession], now: datetime
) -> int:
    async with session_factory() as session:
        service = create_reservation_service(
            session=session,
            slot_repo=create_slot_repository(session=session),
            uow=create_unit_of_work(session=session),
        )
        return await service.expire_no_shows(now)


# 담당 4 : 자동 노쇼 반복. main.py의 lifespan이 앱을 켤 때 시작하고, 끌 때 멈춘다
async def run_no_show_loop(
    session_factory: async_sessionmaker[AsyncSession], interval_seconds: float
) -> None:
    while True:
        await asyncio.sleep(interval_seconds)
        try:
            handled = await expire_no_shows_once(session_factory, seoul_now())
            if handled:
                logger.info("자동 노쇼 처리 %d건", handled)
        except Exception:
            # 한 번 실패해도(DB 끊김 등) 로그만 남기고 다음 반복은 계속한다. 멈출 때(CancelledError)는 여기서 안 잡힌다
            logger.exception("자동 노쇼 처리 실패")


def wire_dependencies(app: FastAPI) -> None:
    app.dependency_overrides.update(
        {
            user_service: create_user_service,  # 담당1
            auth_service: create_auth_service,  # 담당1
        }
    )
