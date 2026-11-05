from typing import Annotated

<<<<<<< HEAD
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from common.database import get_session
from owner.application.service import OwnerService  # 담당 5: 운영자 매니저
from user.application.service import UserService
from user.application.unit_of_work import UnitOfWork
from user.domain.hasher import PasswordHasher
from user.domain.repository import UserRepository
from user.infrastructure.repositories import SQLAlchemyUserRepository
from user.infrastructure.security import BcryptPasswordHasher
from user.infrastructure.unit_of_work import SQLAlchemyUnitOfWork
=======
from common.database import get_session  # 공통: 요청마다 DB 연결 하나
from user.application.service import UserService  # 담당 1: 회원 매니저
from user.domain.repository import UserRepository  # 담당 1: 회원 창고 약속
from user.domain.hasher import PasswordHasher  # 담당 1: 비밀번호 암호화 약속

from user.infrastructure.repositories import SQLAlchemyUserRepository  # 담당 1: 회원 창고
from user.infrastructure.security import BcryptPasswordHasher  # 담당 1: 비밀번호 암호화

from owner.application.service import OwnerService  # 담당 5: 운영자 매니저
from reservation.application.query_service import ReservationQueryService  # 담당 5: 예약 조회 매니저
>>>>>>> bf0be5d666b11eff8ab384164af5c8a031ec4b50

password_hasher: PasswordHasher = BcryptPasswordHasher()


# 담당 1: 회원 창고 공장
def create_user_repository(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> UserRepository:
    return SQLAlchemyUserRepository(session=session)


<<<<<<< HEAD
def create_unit_of_work(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> UnitOfWork:
    return SQLAlchemyUnitOfWork(session=session)


=======
# 담당 1: 회원 매니저 공장
>>>>>>> bf0be5d666b11eff8ab384164af5c8a031ec4b50
def create_user_service(
    repo: Annotated[UserRepository, Depends(create_user_repository)],
    uow: Annotated[UnitOfWork, Depends(create_unit_of_work)],
) -> UserService:
    return UserService(
        repo=repo,
        uow=uow,
        hasher=password_hasher,
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
