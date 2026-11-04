from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from common.errors import AppError, CommonErrorCode, ErrorCode
from common.logger import get_logger
from common.schemas import APIResponse

logger = get_logger(__name__)


# [담당2] 추가
HTTP_STATUS_ERROR_CODES = {
    400: CommonErrorCode.BAD_REQUEST,
    401: CommonErrorCode.UNAUTHORIZED,
    403: CommonErrorCode.FORBIDDEN,
    404: CommonErrorCode.NOT_FOUND,
    405: CommonErrorCode.METHOD_NOT_ALLOWED,
    503: CommonErrorCode.SERVICE_UNAVAILABLE,
}


def _fail(
    error_code: ErrorCode,
    message: str | None = None,
    errors: dict[str, list[str]] | None = None,
) -> JSONResponse:
    body = APIResponse.fail(error_code, message=message, errors=errors)
    return JSONResponse(
        status_code=error_code.status, content=body.model_dump(mode="json")
    )


async def handle_app_error(request: Request, exc: AppError) -> JSONResponse:
    # 요청 줄(상태 코드 포함)은 미들웨어가 남기므로 여기선 code만 덧붙임
    log = logger.error if exc.error_code.status >= 500 else logger.info
    log("%s %s", exc.error_code.code, exc.message)
    return _fail(exc.error_code, exc.message, exc.errors)


# [담당2] 추가
def to_korean_message(error: dict) -> str:
    """Pydantic의 영어 검증 문구를 한국어로 바꿈. 모르는 종류는 원래 문구를 씀"""
    kind = error.get("type", "")
    ctx = error.get("ctx") or {}

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
        # ctx["expected"] 예: "'id' or 'name'"
        expected = str(ctx.get("expected", "")).replace("'", "").replace(" or ", ", ")
        return f"{expected} 중 하나여야 합니다."
    if kind == "value_error":
        # 직접 만든 검증 규칙의 문구. 앞에 붙는 "Value error, "는 뗌
        return str(error.get("msg", "")).removeprefix("Value error, ")
    return str(error.get("msg", "입력값이 올바르지 않습니다."))


async def handle_request_validation(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    errors: dict[str, list[str]] = {}
    for error in exc.errors():
        # loc 첫 칸은 body/query/path 위치라서 필드 이름에서 뺌
        field = ".".join(str(part) for part in error["loc"][1:]) or str(error["loc"][0])
        errors.setdefault(field, []).append(to_korean_message(error))
    return _fail(CommonErrorCode.VALIDATION_ERROR, errors=errors)


# [담당2] 추가
async def handle_http_exception(
    request: Request, exc: StarletteHTTPException
) -> JSONResponse:
    # 표에 없는 상태는 500 이상이면 서버 오류, 아니면 잘못된 요청으로 봄
    default = (
        CommonErrorCode.INTERNAL_SERVER_ERROR
        if exc.status_code >= 500
        else CommonErrorCode.BAD_REQUEST
    )
    error_code = HTTP_STATUS_ERROR_CODES.get(exc.status_code, default)
    body = APIResponse.fail(error_code)
    # 상태 코드는 원래 값 유지, header는 401의 WWW-Authenticate 같은 값을 넘기기 위함
    return JSONResponse(
        status_code=exc.status_code,
        content=body.model_dump(mode="json"),
        headers=exc.headers,
    )


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, handle_app_error)
    app.add_exception_handler(RequestValidationError, handle_request_validation)
    app.add_exception_handler(StarletteHTTPException, handle_http_exception)
