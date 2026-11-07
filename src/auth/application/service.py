from dataclasses import dataclass

from auth.domain.exceptions import InvalidCredentialsError
from auth.domain.provider import TokenProvider
from auth.domain.repository import TokenBlackListRepository
from auth.domain.value_object import AuthRole, AuthenticatedUser

from common.errors import InvalidInputError, UnauthorizedError

from user.domain.hasher import PasswordHasher
from user.domain.repository import UserRepository
from user.domain.value_object import Email


@dataclass(frozen=True)
class IssueToken:
    """로그인 결과, 라우터가 OAuth2 응답으로 바꾼다"""

    access_token: str
    expires_in: int


class AuthService:
    def __init__(
        self,
        user_repo: UserRepository,
        hasher: PasswordHasher,
        token_provider: TokenProvider,
        blacklist_repo: TokenBlackListRepository,
    ):
        self.user_repo = user_repo
        self.hasher = hasher
        self.token_provider = token_provider
        self.blacklist_repo = blacklist_repo

    async def login(self, email: str, password: str) -> IssueToken:
        try:
            user_email = Email(value=email)
        except InvalidInputError:
            raise InvalidCredentialsError()

        user = await self.user_repo.find_by_email(email=user_email)

        if (
            user is None
            or not user.is_active()
            or not self.hasher.verify(
                raw_password=password, hashed_password=user.password_hash
            )
        ):
            raise InvalidCredentialsError()

        token, _, _, expires_in = self.token_provider.create_access_token(
            user_id=user.id
        )

        return IssueToken(access_token=token, expires_in=expires_in)

    async def authenticate(self, token: str) -> AuthenticatedUser:
        # 서명 만료 / 실패하면 401 에러
        payload = self.token_provider.decode_token(token=token)

        # 로그아웃한 토큰
        if await self.blacklist_repo.is_blacklisted(payload.jti):
            raise UnauthorizedError()

        # 사용자 없음 / 탈퇴 역할은 토큰이 아니라 DB의 현재값을 쓴다.

        user = await self.user_repo.find_by_id(payload.user_id)

        if user is None or not user.is_active():
            raise UnauthorizedError()

        return AuthenticatedUser(user_id=user.id, role=AuthRole(user.role.value))
