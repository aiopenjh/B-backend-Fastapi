# [담당1 - 강성수]
import uuid

from user.application.unit_of_work import ConflictError, UnitOfWork
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

    async def signUp(
        self, email: str, raw_password: str, name: str, phone: str
    ) -> User:

        user_email = Email(email)
        if await self.repo.find_by_email(user_email) is not None:
            raise DuplicatedUserError()

        user = User.create(
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
