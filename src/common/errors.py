from enum import Enum, unique
from http import HTTPStatus


class ErrorCode(Enum):
    """에러 코드 enum 공통 믹스인. 멤버 값은 (HTTP 상태, 기본 메시지)"""

    def __init__(self, status: HTTPStatus, message: str):
        self.status = status
        self.message = message

    @property
    def code(self) -> str:
        return self.name


# 값이 같은 멤버는 별칭이 되므로 @unique로 정의 시점에 막음
@unique
class CommonErrorCode(ErrorCode):
    UNAUTHORIZED = (HTTPStatus.UNAUTHORIZED, "인증이 필요합니다.")
    FORBIDDEN = (HTTPStatus.FORBIDDEN, "권한이 없습니다.")
    NOT_FOUND = (HTTPStatus.NOT_FOUND, "리소스를 찾을 수 없습니다.")
    VALIDATION_ERROR = (HTTPStatus.UNPROCESSABLE_CONTENT, "입력값이 올바르지 않습니다.")
    INTERNAL_SERVER_ERROR = (
        HTTPStatus.INTERNAL_SERVER_ERROR,
        "서버 내부 오류가 발생했습니다.",
    )
    SERVICE_UNAVAILABLE = (
        HTTPStatus.SERVICE_UNAVAILABLE,
        "서비스를 일시적으로 사용할 수 없습니다.",
    )


class AppError(Exception):
    """도메인·서비스 규칙 위반. 공통 핸들러가 error_code로 실패 봉투를 만듦"""

    error_code: ErrorCode = CommonErrorCode.INTERNAL_SERVER_ERROR
    # 하위 클래스가 기본 문구만 바꿀 때 지정 (예: NotOwnerError)
    message: str | None = None

    def __init__(
        self,
        message: str | None = None,
        errors: dict[str, list[str]] | None = None,
    ):
        self.message = message or self.message or self.error_code.message
        self.errors = errors or {}
        super().__init__(self.message)


class UnauthorizedError(AppError):
    error_code = CommonErrorCode.UNAUTHORIZED


class ForbiddenError(AppError):
    error_code = CommonErrorCode.FORBIDDEN


class NotFoundError(AppError):
    error_code = CommonErrorCode.NOT_FOUND


class InvalidInputError(AppError):
    error_code = CommonErrorCode.VALIDATION_ERROR
