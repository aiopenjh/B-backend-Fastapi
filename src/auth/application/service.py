from dataclasses import dataclass

from auth.domain.exceptions import InvalidCredentialsError
from auth.domain.provider import TokenProvider
from auth.domain.repository import TokenBlackListRepository
from auth.domain.value_object import AuthRole, AuthenticatedUser
from auth.domain.token_entities import BlackListToken

from common.errors import InvalidInputError, UnauthorizedError
from common.unit_of_work import ConflictError, UnitOfWork

from user.domain.hasher import PasswordHasher
from user.domain.repository import UserRepository
from user.domain.value_object import Email


@dataclass(frozen=True)
class IssuedToken:
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
        uow: UnitOfWork,
    ):
        self.user_repo = user_repo
        self.hasher = hasher
        self.token_provider = token_provider
        self.blacklist_repo = blacklist_repo
        self.uow = uow

    async def login(self, email: str, password: str) -> IssuedToken:
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

        return IssuedToken(access_token=token, expires_in=expires_in)

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

    async def logout(self, token: str) -> None:
        # 서명, 만료가 잘못된 토큰은 401
        payload = self.token_provider.decode_token(token=token)

        # 이미 로그아웃한 토큰도 401
        if await self.blacklist_repo.is_blacklisted(payload.jti):
            raise UnauthorizedError()

        # 만료 시각까지만 막으면 된다. 그 뒤에는 서명 검사에서 이미 거부된다.
        await self.blacklist_repo.add(
            BlackListToken(
                jti=payload.jti, user_id=payload.user_id, expired_at=payload.exp
            )
        )

        try:
            await self.uow.commit()
        except ConflictError:
            # 같은 토큰으로 동시에 로그아웃하면 두 번째는 jti UNIQUE에 걸린다
            raise UnauthorizedError()
