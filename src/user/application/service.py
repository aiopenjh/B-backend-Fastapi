from user.domain.hasher import PasswordHasher
from user.domain.repository import UserRepository
from user.domain.exceptions import DuplicatedUserError
from user.domain.user import User


class UserService:
    def __init__(self, repo: UserRepository, hasher: PasswordHasher):
        self.repo = repo
        self.hasher = hasher

    async def signUp(
        self, email: str, raw_password: str, name: str, phone: str
    ) -> User:

        email = email.strip().lower()
        if await self.repo.find_by_email(email) is not None:
            raise DuplicatedUserError()

        user = User.create(
            email=email,
            raw_password=raw_password,
            name=name,
            phone=phone,
            hasher=self.hasher,
        )

        return await self.repo.save(user)
