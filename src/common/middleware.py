import logging
import os
import time
import uuid

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from common.context import request_id_var
from common.errors import CommonErrorCode
from common.schemas import APIResponse

logger = logging.getLogger(__name__)

DEFAULT_CORS_ORIGINS = "http://localhost:3000"


def _allowed_origins() -> list[str]:
    # CORS_ORIGINS: 쉼표 구분 목록, 공백·빈 항목은 무시
    raw = os.environ.get("CORS_ORIGINS", DEFAULT_CORS_ORIGINS)
    return [o.strip() for o in raw.split(",") if o.strip()]


def register_middleware(app: FastAPI) -> None:
    @app.middleware("http")
    async def log_request(request: Request, call_next):
        request_id = f"req_{uuid.uuid4().hex[:12]}"
        # call_next 전에 설정해야 라우터·예외 핸들러의 APIResponse가 같은 id를 읽음
        token = request_id_var.set(request_id)
        start = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            # 여기서 잡지 않으면 바깥 ServerErrorMiddleware가 500을 만들어 request_id·헤더·로그가 모두 빠짐
            logger.exception(
                "%s unhandled error %s %s", request_id, request.method, request.url.path
            )
            error_code = CommonErrorCode.INTERNAL_SERVER_ERROR
            response = JSONResponse(
                status_code=error_code.status,
                content=APIResponse.fail(error_code).model_dump(mode="json"),
            )
        finally:
            request_id_var.reset(token)
        elapsed = time.perf_counter() - start
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Process-Time"] = f"{elapsed:.4f}"
        logger.info(
            "%s %s %s %s %.4fs",
            request_id,
            request.method,
            request.url.path,
            response.status_code,
            elapsed,
        )
        return response

    # 나중에 추가한 미들웨어가 바깥쪽 → CORS가 최외곽에서 preflight 처리
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_allowed_origins(),
        allow_methods=["*"],
        allow_headers=["Authorization", "Content-Type"],
        # 노출하지 않으면 브라우저 JS가 응답 헤더를 읽지 못함
        expose_headers=["X-Request-ID"],
    )
