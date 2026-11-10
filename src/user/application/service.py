# [담당1 - 강성수]
import asyncio
import uuid

from common.unit_of_work import ConflictError, UnitOfWork
from user.domain.exceptions import DuplicatedUserError, UserNotFoundError
from user.domain.hasher import PasswordHasher
from user.domain.repository import UserRepository
from user.domain.user import Role, User
from user.domain.value_object import Email


class UserService:

    def __init__(self, repo: UserRepository, uow: UnitOfWork, hasher: PasswordHasher):
        self.repo = repo
        self.uow = uow
        self.hasher = hasher

    async def sign_up(
        self, email: str, raw_password: str, name: str, phone: str
    ) -> User:

        user_email = Email(email)
        if await self.repo.find_by_email(user_email) is not None:
            raise DuplicatedUserError()

        # User.create 안에서 bcrypt 해시(약 0.25초)를 한다. 그동안 DB 연결을 붙잡지 않게
        # 읽기 트랜잭션을 끝내고, 이벤트 루프를 막지 않게 스레드에서 만든다.
        # 그 사이 같은 이메일 가입은 commit의 UNIQUE 충돌로 잡힌다
        await self.uow.release()
        user = await asyncio.to_thread(
            User.create,
            email=user_email,
            raw_password=raw_password,
            name=name,
            phone=phone,
            hasher=self.hasher,
        )

        saved = await self.repo.save(user)
        try:
            await self.uow.commit()
        except ConflictError:
            # 동시 가입처럼 find_by_email 확인을 지나친 중복은 commit에서 드러난다
            raise DuplicatedUserError()
        return saved

    async def change_role(self, user_id: uuid.UUID, new_role: Role) -> User:
        user = await self.repo.find_by_id(user_id)
        if user is None or not user.is_active():
            raise UserNotFoundError()

        user.change_owner_role(new_role)

        saved = await self.repo.save(user)
        await self.uow.commit()
        return saved

    async def get_user(self, user_id: uuid.UUID) -> User:
        user = await self.repo.find_by_id(user_id)
        if user is None or not user.is_active():
            raise UserNotFoundError()

        return user
