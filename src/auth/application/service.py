import asyncio
from dataclasses import dataclass

from auth.domain.exceptions import (
    InvalidCredentialsError,
    TooManyLoginAttemptsError,
)
from auth.domain.limiter import (
    LoginAttemptKey,
    LoginAttemptLimiter,
    LoginAttemptReservation,
)
from auth.domain.provider import TokenProvider
from auth.domain.repository import TokenBlackListRepository
from auth.domain.value_object import AuthRole, AuthenticatedUser
from auth.domain.token_entities import BlackListToken

from common.errors import InvalidInputError, UnauthorizedError
from common.unit_of_work import ConflictError, UnitOfWork

from user.domain.hasher import PasswordHasher
from user.domain.repository import UserRepository
from user.domain.value_object import Email


# 계정이 없거나 탈퇴했을 때도 같은 검증 작업을 하려고 쓰는 비밀번호.
# 이 값으로는 로그인할 수 없다 (계정이 있어야 성공하므로 비교용으로만 쓰임)
DUMMY_PASSWORD = "timing-equalizer-password-1!"


def make_dummy_hash(hasher: PasswordHasher) -> str:
    """앱 시작 때 한 번만 만든다 (container). 요청 중에 만들면 그만큼 느려져
    없는 계정의 응답 시간이 달라진다"""
    return hasher.hash(DUMMY_PASSWORD)


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
        login_limiter: LoginAttemptLimiter,
        client_ip: str | None,
        dummy_hash: str,
    ):
        self.user_repo = user_repo
        self.hasher = hasher
        self.token_provider = token_provider
        self.blacklist_repo = blacklist_repo
        self.uow = uow
        self.login_limiter = login_limiter
        # 요청마다 만들어지는 서비스라 요청한 쪽 IP를 함께 받는다 (container가 넣음)
        self.client_ip = client_ip
        self.dummy_hash = dummy_hash

    async def login(self, email: str, password: str) -> IssuedToken:
        try:
            user_email = Email(value=email)
        except InvalidInputError:
            raise InvalidCredentialsError()

        key = LoginAttemptKey(email=user_email.value, client_ip=self.client_ip)
        # 확인과 동시에 시도를 먼저 기록한다 (await 전). 막힌 요청은 DB 조회와 해시를 하지 않는다
        reservation = self.login_limiter.try_acquire(key)
        if reservation is None:
            raise TooManyLoginAttemptsError()

        verification: asyncio.Task[bool] | None = None
        try:
            user = await self.user_repo.find_by_email(email=user_email)
            # 로그인할 수 있는 계정만 남긴다 (없음·탈퇴는 None). 타입 검사기도 None을 구분한다
            active_user = user if user is not None and user.is_active() else None

            # bcrypt는 약 0.25초 걸린다. 그동안 DB 연결을 붙잡지 않게 읽기 트랜잭션을 끝내고,
            # 이벤트 루프를 막지 않게 스레드에서 검증한다.
            # 계정이 없거나 탈퇴했어도 미리 만든 더미 해시로 같은 검증을 한 번 해서,
            # 응답 시간으로 가입 여부를 알 수 없게 한다
            await self.uow.release()
            verification = asyncio.create_task(
                asyncio.to_thread(
                    self.hasher.verify,
                    raw_password=password,
                    hashed_password=(
                        active_user.password_hash
                        if active_user is not None
                        else self.dummy_hash
                    ),
                )
            )
            verified = await asyncio.shield(verification)
        except asyncio.CancelledError:
            if verification is None:
                self.login_limiter.release(reservation)
            else:
                # 요청 취소로 작업 스레드가 멈추지는 않는다. 실제 종료 후 예약을 정리한다.
                verification.add_done_callback(
                    lambda task: self._finish_cancelled_verification(reservation, task)
                )
            raise
        except Exception:
            # 비밀번호와 상관없는 오류는 시도로 세지 않는다 (DB 장애 뒤 사용자가 막히지 않게)
            self.login_limiter.release(reservation)
            raise

        if active_user is None or not verified:
            self.login_limiter.record_failure(reservation)
            raise InvalidCredentialsError()

        try:
            token, _, _, expires_in = self.token_provider.create_access_token(
                user_id=active_user.id
            )
        except Exception:
            # 토큰을 못 받았으면 로그인 성공이 아니다. 이전 실패 이력은 남기고,
            # 비밀번호 실패도 아니므로 이 요청의 예약만 돌려준다
            self.login_limiter.release(reservation)
            raise

        # 토큰 발급까지 끝나야 성공을 확정하고 이전 실패 이력을 지운다
        self.login_limiter.reset(reservation)
        return IssuedToken(access_token=token, expires_in=expires_in)

    def _finish_cancelled_verification(
        self, reservation: LoginAttemptReservation, task: asyncio.Task[bool]
    ) -> None:
        if task.cancelled() or task.exception() is not None:
            self.login_limiter.release(reservation)
        else:
            # 응답 없이 끝난 검증은 다른 요청의 실패 이력을 초기화하지 않는다.
            self.login_limiter.record_failure(reservation)

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
