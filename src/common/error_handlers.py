from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from common.errors import AppError, CommonErrorCode, ErrorCode
from common.logger import get_logger
from common.schemas import APIResponse

logger = get_logger(__name__)


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


async def handle_request_validation(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    errors: dict[str, list[str]] = {}
    for error in exc.errors():
        # loc 첫 칸은 body/query/path 위치라서 필드 이름에서 뺌
        field = ".".join(str(part) for part in error["loc"][1:]) or str(error["loc"][0])
        errors.setdefault(field, []).append(error["msg"])
    return _fail(CommonErrorCode.VALIDATION_ERROR, errors=errors)


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, handle_app_error)
    app.add_exception_handler(RequestValidationError, handle_request_validation)
