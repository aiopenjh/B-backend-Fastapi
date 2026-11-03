from datetime import datetime, timedelta, timezone
from typing import Annotated

from pydantic import BaseModel, Field

from common.context import request_id_var
from common.errors import ErrorCode

# ZoneInfo는 시간대 DB가 없는 환경(Windows 기본)에서 import 시 실패. 한국은 서머타임이 없어 고정 오프셋과 같음
SEOUL = timezone(timedelta(hours=9), "Asia/Seoul")


class APIResponse[T](BaseModel):
    success: Annotated[bool, Field(description="성공 처리 여부")]
    code: Annotated[
        str,
        Field(description="성공 시 'OK', 실패 시 에러 코드 (API_SPEC 에러 코드 표)"),
    ]
    message: Annotated[str | None, Field(description="성공 또는 실패시 메시지")] = None
    errors: Annotated[
        dict[str, list[str]] | None,
        Field(description="실패시 필드 이름 → 메시지 목록, 성공 시 null"),
    ] = None
    data: Annotated[T | None, Field(description="성공 응답 데이터")] = None
    request_id: Annotated[
        str | None,
        Field(
            default_factory=request_id_var.get,
            description="요청 id (X-Request-ID 헤더와 같은 값)",
        ),
    ]
    responded_at: Annotated[
        datetime,
        Field(
            default_factory=lambda: datetime.now(SEOUL),
            description="응답 시각 (Asia/Seoul)",
        ),
    ]

    @classmethod
    def ok(
        cls,
        data: T | None = None,
        message: str = "요청이 성공적으로 처리되었습니다.",
    ) -> APIResponse[T]:
        return cls(success=True, code="OK", message=message, data=data)  # type: ignore

    @classmethod
    def fail(
        cls,
        error_code: ErrorCode,
        message: str | None = None,
        errors: dict[str, list[str]] | None = None,
    ) -> APIResponse[None]:
        return APIResponse[None](
            success=False,
            code=error_code.code,
            message=message or error_code.message,
            errors=errors or {},
        )  # type: ignore
