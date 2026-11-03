from contextvars import ContextVar

# 요청 로그 미들웨어가 요청마다 설정. 요청 밖에서는 None
request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)
