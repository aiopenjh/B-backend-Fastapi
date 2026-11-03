from enum import Enum, unique
from http import HTTPStatus


class ErrorCode:
    """에러 코드 enum 공통 믹스인. 멤버 값은 (HTTP 상태, 기본 메시지)"""

    def __init__(self, status: HTTPStatus, message: str):
        self.status = status
        self.message = message

    @property
    def code(self) -> str:
        return self.name


# 값이 같은 멤버는 별칭이 되므로 @unique로 정의 시점에 막음
@unique
class CommonErrorCode(ErrorCode, Enum):
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


# [담당2] 코드 추가


class AppError(Exception):
    """모든 업무 예외의 부모 클래스"""

    def __init__(
        self,
        message: str,
        status_code: int = 400,
        error_code: str = "BAD_REQUEST",
        errors: dict | None = None,
    ):
        self.message = message
        self.status_code = status_code
        self.error_code = error_code
        self.errors = errors
        super().__init__(message)

    @classmethod
    def from_code(
        cls,
        error_code: ErrorCode,
        message: str | None = None,
        errors: dict | None = None,
    ) -> "AppError":

        return cls(
            message=message or error_code.message,
            status_code=int(error_code.status),
            error_code=error_code.code,
            errors=errors,
        )


class _CommonException(AppError):

    default: CommonErrorCode

    def __init__(
        self,
        message: str | None = None,
        error_code: str | None = None,
        errors: dict | None = None,
    ):
        super().__init__(
            message=message or self.default.message,
            status_code=int(self.default.status),
            error_code=error_code or self.default.code,
            errors=errors,
        )


class UnauthorizedException(_CommonException):
    """401: 토큰 없음. 만료. 로그아웃한 토큰, 로그인 실패"""

    default = CommonErrorCode.UNAUTHORIZED


class ForbiddenException(_CommonException):
    """403: 운영자가 아님(역할), 남의 식당(소유)"""

    default = CommonErrorCode.FORBIDDEN


class NotFoundException(_CommonException):
    """404: 없는 리소스, 관련 없는 사람에게 숨긴 리소스"""

    default = CommonErrorCode.NOT_FOUND


class ServiceUnavailableException(_CommonException):
    """503: DB 연결 실패"""

    default = CommonErrorCode.SERVICE_UNAVAILABLE


class ValidationException(AppError):
    """422: 도메인 규칙으로 검사한 입력 오류"""

    def __init__(
        self,
        message: str | None = None,
        error_code: str | None = None,
        field_errors: dict | None = None,
    ):
        default = CommonErrorCode.VALIDATION_ERROR

        errors = {
            field: ", ".join(msgs) if isinstance(msgs, list) else str(msgs)
            for field, msgs in (field_errors or {}).items()
        }
        super().__init__(
            message=message or default.message,
            status_code=int(default.status),
            error_code=error_code or default.code,
            errors=errors,
        )


class BadRequestException(AppError):
    """400: 잘못된 요청"""

    def __init__(
        self,
        message: str,
        error_code: str = "BAD_REQUEST",
        errors: dict | None = None,
    ):
        super().__init__(
            message=message, status_code=400, error_code=error_code, errors=errors
        )


class ConflictException(AppError):
    """409: 상태 충돌 (예: SLOT_SOLD_OUT, DUPLICATE_RESERVATION)"""

    def __init__(
        self,
        message: str = "리소스가 이미 존재합니다.",
        error_code: str = "CONFLICT",
        errors: dict | None = None,
    ):
        super().__init__(
            message=message, status_code=409, error_code=error_code, errors=errors
        )
