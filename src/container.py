from fastapi import Depends

from sqlalchemy.ext.asyncio import AsyncSession
from typing import Annotated

from common.database import get_session  # 공통: 요청마다 DB 연결 하나
from user.application.service import UserService  # 담당 1: 회원 매니저
from user.domain.repository import UserRepository  # 담당 1: 회원 창고 약속
from user.domain.hasher import PasswordHasher  # 담당 1: 비밀번호 암호화 약속

from user.infrastructure.repositories import SQLAlchemyUserRepository  # 담당 1: 회원 창고
from user.infrastructure.security import BcryptPasswordHasher  # 담당 1: 비밀번호 암호화

from owner.application.service import OwnerService  # 담당 5: 운영자 매니저
from reservation.application.query_service import ReservationQueryService  # 담당 5: 예약 조회 매니저

password_hasher: PasswordHasher = BcryptPasswordHasher()


# 담당 1: 회원 창고 공장
def create_user_repository(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> UserRepository:
    return SQLAlchemyUserRepository(session=session)


# 담당 1: 회원 매니저 공장
def create_user_service(
    repo: Annotated[UserRepository, Depends(create_user_repository)],
) -> UserService:
    return UserService(repo=repo, hasher=password_hasher)


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
