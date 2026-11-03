# [담당2]

"""에러를 팀 공통 응답 형식으로 바꾸는 전역 예외 처리기

    {"error": {"code": "NOT_FOUND", "message": "...", "details": {}, "request_id": "req_ab12cd"}}

main.py에서 register_exception_handlers(app) 한 줄로 등록한다.
"""

import logging
import uuid

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from common.errors import AppError, CommonErrorCode

logger = logging.getLogger(__name__)

# FastAPI/Starlette가 직접 던지는 HTTPException용 (없는 주소, 토큰 없음, database.py의 503등)
# 코드와 메시지는 팀의 CommonErrorCode를 그대로 쓴다.

HTTP_STATUS_ERROR_CODES = {
    401: CommonErrorCode.UNAUTHORIZED,
    403: CommonErrorCode.FORBIDDEN,
    404: CommonErrorCode.NOT_FOUND,
    503: CommonErrorCode.SERVICE_UNAVAILABLE,
}


def http_error_info(status_code: int) -> tuple[str, str]:
    """HTTP 상태 코드 -> (에러 code, 기본 메시지)"""
    error_code = HTTP_STATUS_ERROR_CODES.get(status_code)
    if error_code:
        return error_code.code, error_code.message
    if status_code == 405:  # CommonErrorCode에 없는 상태
        return "METHOD_NOT_ALLOWED", "허용되지 않은 요청 방식입니다."
    return "HTTP_ERROR", "요청을 처리할 수 없습니다."


def get_request_id(request: Request) -> str:
    """미들웨어가 request.state.request_id에 넣어 둔 값을 쓰고, 없으면 새로 만든다."""
    request_id = getattr(request.state, "request_id", None)
    return request_id or f"req_{uuid.uuid4().hex[:6]}"


def make_error_body(code: str, message: str, details: dict, request_id: str) -> dict:
    return {
        "error": {
            "code": code,
            "message": message,
            "details": details,
            "request_id": request_id,
        }
    }


def to_korean_message(err: dict) -> str:
    """Pydantic이 만든 영어 검증 오류를 한국어 문구로 바꾼다. 모르는 종류는 원래 문구를 쓴다."""
    kind = err.get("type", "")
    ctx = err.get("ctx") or {}

    if kind == "missing":
        return "필수 입력 항목입니다."
    if kind in ("int_parsing", "int_type"):
        return "정수여야 합니다."
    if kind in ("float_parsing", "float_type"):
        return "숫자여야 합니다."
    if kind == "string_type":
        return "문자열이어야 합니다."
    if kind == "bool_parsing":
        return "true 또는 false여야 합니다."
    if kind == "greater_than_equal":
        return f"{ctx['ge']} 이상이어야 합니다."
    if kind == "greater_than":
        return f"{ctx['gt']}보다 커야 합니다."
    if kind == "less_than_equal":
        return f"{ctx['le']} 이하여야 합니다."
    if kind == "less_than":
        return f"{ctx['lt']}보다 작아야 합니다."
    if kind == "string_too_short":
        return f"{ctx['min_length']}자 이상이어야 합니다."
    if kind == "string_too_long":
        return f"{ctx['max_length']}자 이하여야 합니다."
    if kind == "literal_error":
        # ctx["expected"] 예 : "'id', 'name' or 'newest'"
        expected = str(ctx.get("expected", "")).replace("'", "").replace(" or ", ", ")
        return f"{expected} 중 하나여야 합니다."
    if kind == "value_error":
        # 직접 만든 검증 규칙의 문구. 앞에 붙는 "Value error, "는 떼어 낸다.
        return str(err.get("msg", "")).removeprefix("Value error, ")
    return str(err.get("msg", "입력값이 올바르지 않습니다."))


def to_field_name(loc: tuple) -> str:
    """('query', 'page_size') -> 'page_size', ('body', 'menus', 0, 'price') -> 'menus.0.price'"""
    parts = [str(item) for item in loc[1:]]
    return ".".join(parts) if parts else str(loc[0])


def register_exception_handlers(app: FastAPI) -> None:
    # 비즈니스 예외 (AppError와 그 자식: NotFoundException, ForbiddenException...)
    @app.exception_handler(AppError)
    async def app_exception_handler(request: Request, exc: AppError):
        if exc.status_code >= 500:
            logger.error("비즈니스 서버 오류 [%s]: %s", exc.error_code, exc.message)
        else:
            logger.warning(
                "클라이언트 예외 요청 [%s]: %s (path: %s, method: %s)",
                exc.error_code,
                exc.message,
                request.url.path,
                request.method,
            )

        return JSONResponse(
            status_code=exc.status_code,
            content=make_error_body(
                exc.error_code, exc.message, exc.errors or {}, get_request_id(request)
            ),
        )

    # Pydantic 입력 검증 실패 (422)
    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        details: dict[str, str] = {}
        for err in exc.errors():
            field_name = to_field_name(err["loc"])
            details.setdefault(field_name, to_korean_message(err)) # 같은 필드는 첫 오류만

        logger.warning(
            "요청 파라미터 유효성 검증 실패 (path: %s, method: %s): %s",
            request.url.path,
            request.method,
            details,
        )

        return JSONResponse(
            status_code=422,
            content=make_error_body(
                CommonErrorCode.VALIDATION_ERROR.code,
                CommonErrorCode.VALIDATION_ERROR.message,
                details,
                get_request_id(request),
            ),
        )

    # FastAPI/Starlette가 직접 던지는 HTTPException
    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException):
        code, message = http_error_info(exc.status_code)
        return JSONResponse(
            status_code=exc.status_code,
            content=make_error_body(code, message, {}, get_request_id(request)),
            headers=exc.headers, # 예: 401의 WWW-Authenticate
        )

    # 처리되지 않은 시스템 내부 오류 (500)
    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        request_id = get_request_id(request)
        logger.exception(
            "처리되지 않은 시스템 오류 발생 (path: %s, method: %s, request_id: %s)",
            request.url.path,
            request.method,
            request_id,
        ) #자세한 내용은 로그에만 남기고 응답에는 넣지 않는다

        return JSONResponse(
            status_code=500,
            content=make_error_body(
                CommonErrorCode.INTERNAL_SERVER_ERROR.code,
                CommonErrorCode.INTERNAL_SERVER_ERROR.message,
                {},
                request_id,
            ),
        )