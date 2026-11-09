from functools import lru_cache
from typing import Annotated

from fastapi import Depends, FastAPI
from sqlalchemy.ext.asyncio import AsyncSession

from common.database import get_session  # 공통: 요청마다 DB 연결 하나

from auth.application.service import AuthService
from auth.domain.provider import TokenProvider
from auth.domain.repository import TokenBlackListRepository
from auth.infrastructure.repositories import SQLAlchemyTokenBlackListRepository
from auth.infrastructure.security import JwtTokenProvider
from auth.presentation.dependencies import auth_service

from owner.application.service import OwnerService  # 담당 5: 운영자 매니저

from reservation.application.query_service import (
    ReservationQueryService,
)  # 담당 5: 예약 조회 매니저
from reservation.application.service import ReservationService # 담당 4 : 예약 매니저
from reservation.infrastructure.repositories import (
    SQLAlchemyReservationRepository,
) # 담당 4 : 예약 창고

from slot.infrastructure.repositories import SQLAlchemySlotRepository # 담당 3 : 슬롯 창고

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
from user.presentation.dependencies import user_repository, user_service

password_hasher: PasswordHasher = BcryptPasswordHasher()


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
    user_repo: Annotated[UserRepository, Depends(create_user_repository)],
    blacklist_repo: Annotated[
        TokenBlackListRepository, Depends(create_token_blacklist_repository)
    ],
    token_provider: Annotated[TokenProvider, Depends(get_token_provider)],
) -> AuthService:
    return AuthService(
        user_repo=user_repo,
        hasher=password_hasher,
        blacklist_repo=blacklist_repo,
        token_provider=token_provider,
    )


# 담당 5: 운영자 매니저 공장
def create_owner_service(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> OwnerService:
    return OwnerService(session)


# 담당 5: 예약 조회 매니저 공장
def create_reservation_query_service(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ReservationQueryService:
    return ReservationQueryService(session)


# 담당 4 : 예약 매니저 공장 (생성, 취소)
def create_reservation_service(
    session: Annotated[AsyncSession, Depends(get_session)],
    uow: Annotated[UnitOfWork, Depends(create_unit_of_work)],
) -> ReservationService:
    return ReservationService(
        reservation_repo=SQLAlchemyReservationRepository(session),
        slot_repo=SQLAlchemySlotRepository(session),
        uow=uow,
)


# 담당 2: 식당 매니저 공장
def create_restaurant_service(
    session: Annotated[AsyncSession, Depends(get_session)],
    uow: Annotated[UnitOfWork, Depends(create_unit_of_work)],
) -> RestaurantService:
    return RestaurantService(repo=RestaurantRepository(session), uow=uow)


def wire_dependencies(app: FastAPI) -> None:
    app.dependency_overrides.update(
        {
            user_repository: create_user_repository,  # 담당1
            user_service: create_user_service,  # 담당1
            auth_service: create_auth_service,  # 담당1
        }
    )
