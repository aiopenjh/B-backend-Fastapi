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
