from dataclasses import field
from typing import Generic, TypeVar
from fastapi import status

T = TypeVar("T")


class SharedException(Exception, Generic[T]):
    """예외 공통 부모 클래스"""

    def __init__(
        self,
        message: str,
        status_code: int = status.HTTP_400_BAD_REQUEST,
        error_code: str = "BAD_REQUEST",
        errors: T | None = None,
    ):
        self.message = message
        self.status_code = status_code
        self.error_code = error_code
        self.errors = errors
        super().__init__(message)


class BadRequestException(SharedException[T]):
    def __init__(
        self,
        message: str,
        error_code: str = "BAD_REQUEST",
        errors: T | None = None,
    ):
        super().__init__(
            message=message,
            status_code=status.HTTP_400_BAD_REQUEST,
            error_code=error_code,
            errors=errors,
        )


class UnauthorizedException(SharedException[None]):
    def __init__(
        self,
        message: str = "인증되지 않은 사용자입니다.",
        error_code: str = "UNAUTHORIZED",
    ):
        super().__init__(
            message=message,
            status_code=status.HTTP_401_UNAUTHORIZED,
            error_code=error_code,
            errors=None,
        )


class ForbiddenException(SharedException[None]):
    def __init__(
        self,
        message: str = "리소스에 접근할 권한이 없습니다.",
        error_code: str = "FORBIDDEN",
    ):
        super().__init__(
            message=message,
            status_code=status.HTTP_403_FORBIDDEN,
            error_code=error_code,
            errors=None,
        )


class NotFoundException(SharedException[None]):
    def __init__(
        self,
        message: str = "리소스를 찾을 수 없습니다.",
        error_code: str = "NOT_FOUND",
    ):
        super().__init__(
            message=message,
            status_code=status.HTTP_404_NOT_FOUND,
            error_code=error_code,
            errors=None,
        )


class ConflictException(SharedException[None]):
    def __init__(
        self,
        message: str = "리소스가 이미 존재합니다",
        error_code: str = "CONFLICT",
    ):
        super().__init__(
            message=message,
            status_code=status.HTTP_409_CONFLICT,
            error_code=error_code,
            errors=None,
        )


class ValidationException(SharedException[dict[str, list[str]]]):
    def __init__(
        self,
        message: str = "유효성 검사에 실패했습니다.",
        error_code: str = "VALIDATION_ERROR",
        field_errors: dict[str, list[str]] | None = None,
    ):
        super().__init__(
            message=message,
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            error_code=error_code,
            errors=field_errors or {},
        )
