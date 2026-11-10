# [시연용] 서버 로그 창을 화면 옆에 붙여서 앱을 켠다 — 팀 프로젝트 코드(src/)는 고치지 않는다
"""실행 (저장소 맨 위 폴더에서):

    uv run uvicorn demo.log_panel_app:app --port 8000

- 팀 앱(src/main.py의 app)을 그대로 가져와서, 바깥에 미들웨어 하나만 덧씌운다.
- /ui 화면(HTML)이 나갈 때 </body> 앞에 "서버 로그" 창을 끼워 넣는다.
- 로그는 터미널(cmd)에 찍히는 것과 같은 줄을 최근 60줄만 메모리에 모은다.
- 시연·테스트용이다. 로그에 내부 정보가 있으니 배포에는 쓰지 않는다.
"""

import logging
import re
import sys
from collections import deque
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Annotated
from urllib.parse import parse_qs, urlparse

from fastapi import Depends, Form
from jinja2 import Environment, FileSystemLoader, select_autoescape
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import RedirectResponse, Response

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "src"))  # 팀 코드(src)를 import 할 수 있게

import seed  # 시드 계정 (이메일·비밀번호) — 계정 바꾸기에서만 읽음
from auth.application.service import AuthService  # 담당 1 로그인 매니저 (그대로 부름)
from common.errors import AppError
from container import create_auth_service
from main import app  # 팀 앱 그대로 (위에서 src 경로를 넣은 뒤에 가져옴)
from web_auth import COOKIE_NAME, COOKIE_PATH, home_url

# 시연 계정 바꾸기: 시연 앱에서는 로그 창 위에 항상 고정 (로그인 전·후, 누구로 있든 언제든 바꿈)
ACCOUNTS = {"admin": ("관리자", seed.ADMIN[0], seed.ADMIN_PASSWORD)} | {
    email.split("@")[0].replace(".", "_"): (name, email, seed.SEED_PASSWORD)
    for email, name, _, _ in sorted(seed.USERS, key=lambda user: user[3] != "OWNER")  # 운영자 먼저, 그다음 손님
}

LOGIN_PAGES = {"/ui", "/ui/login"}  # 로그인 폼이 있는 화면
DETAIL_PAGE = re.compile(r"^/ui/restaurants/\d+$")  # 식당 상세(예약하기) 화면
CLOSED_SLOT = re.compile(r'(<input type="radio" name="slot_id"[^>]*?)\s+disabled')  # 마감·자리 부족 시간 버튼
# 화면이 잡아서 안내로 바꾼 실패 코드 → 원래 HTTP 상태 (로그 창에 같이 찍음)
FAIL_STATUS = {"NOT_FOUND": 404, "NOT_THIS_RESTAURANT": 404}
STATUS = re.compile(r"(?<=\s)([1-5])\d\d(?=\s|$)")  # 로그 줄 속 HTTP 상태 번호 (200·401·500 …)
logger = logging.getLogger("demo")


@dataclass
class LogLine:
    time: str
    level: str
    text: str
    tone: str  # ok · warn(4xx) · error(5xx·오류)
    code: str = ""  # 줄 속 상태 번호 (없으면 빈칸) — 화면에서 이 번호만 색 배지로
    before: str = ""  # 번호 앞 글자
    after: str = ""  # 번호 뒤 글자


class RecentLogs(logging.Handler):
    """최근 로그 몇십 줄만 메모리에 모아 둔다 (오래된 줄은 자동으로 밀려남)"""

    def __init__(self, size: int = 60):
        super().__init__()
        self.size = size
        self.lines: deque[LogLine] = deque(maxlen=size)

    def emit(self, record: logging.LogRecord) -> None:
        text = record.getMessage()
        if record.exc_info and record.exc_info[1] is not None:
            error = record.exc_info[1]
            text += f" → {type(error).__name__}: {error}"  # 터미널의 긴 Traceback 대신 마지막 한 줄만
        line = f"{record.name}: {text}"
        status = STATUS.search(line)
        if record.levelno >= logging.ERROR or (status and status.group(1) == "5"):
            tone = "error"
        elif record.levelno >= logging.WARNING or (status and status.group(1) == "4") or record.name == "common.error_handlers":
            tone = "warn"  # 4xx 요청 줄, 경고, API 오류 코드 줄(FORBIDDEN 등)
        else:
            tone = "ok"
        self.lines.append(
            LogLine(
                time=datetime.fromtimestamp(record.created).strftime("%H:%M:%S"),
                level=record.levelname,
                text=line,
                tone=tone,
                code=status.group(0) if status else "",
                before=line[: status.start()] if status else line,
                after=line[status.end():] if status else "",
            )
        )

    def latest(self) -> list[LogLine]:
        return list(reversed(self.lines))  # 최신 줄이 맨 위


recent_logs = RecentLogs()
for name in ("", "uvicorn.error"):  # "" = 팀 공통 로거가 쓰는 맨 위 로거
    logging.getLogger(name).addHandler(recent_logs)

views = Environment(loader=FileSystemLoader(HERE / "templates"), autoescape=select_autoescape())
STYLE = (HERE / "log_panel.css").read_text(encoding="utf-8")


def explain(request: Request, response: Response) -> None:
    """화면이 오류를 잡아서 안내로 바꾼 경우, 무엇이 실패했는지 한 줄 더 남긴다"""
    path = request.url.path
    if request.method == "POST" and path == "/ui/login" and response.status_code == 401:
        logger.warning("화면 로그인 실패 401 (이메일 또는 비밀번호가 틀림)")
    location = response.headers.get("location", "")
    query = parse_qs(urlparse(location).query)
    if fail := query.get("fail"):
        logger.warning("화면 예약하기 실패 %s %s", FAIL_STATUS.get(fail[0], 409), fail[0])
    if cancel_fail := query.get("cancel_fail"):
        logger.warning("화면 예약 취소 실패 %s %s", FAIL_STATUS.get(cancel_fail[0], 409), cancel_fail[0])
    if response.status_code in (403, 404) and path.startswith("/ui"):
        logger.warning("화면 안내 %s %s", response.status_code, path)


class LogPanelMiddleware(BaseHTTPMiddleware):
    """/ui 화면(HTML)에 서버 로그 창을 끼워 넣는다. API(JSON)·파일은 그대로 통과"""

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)  # 안쪽 팀 미들웨어가 이 요청 로그를 이미 남긴 뒤
        explain(request, response)
        is_page = response.headers.get("content-type", "").startswith("text/html")
        if not (is_page and request.url.path.startswith("/ui")):
            return response
        body = b"".join([chunk async for chunk in response.body_iterator])
        panel = views.get_template("log_panel.html").render(
            log_panel=recent_logs, style=STYLE, accounts=ACCOUNTS, back=request.url.path,
        )
        page = body.decode("utf-8").replace("</body>", panel + "\n</body>", 1)
        if request.url.path in LOGIN_PAGES:
            # 시연용: 브라우저의 이메일 형식 검사를 꺼서 엉터리 값도 서버까지 가게 함 (로그에 401이 찍힘)
            page = page.replace("<form", "<form novalidate", 1)
        if DETAIL_PAGE.match(request.url.path):
            # 시연용: 마감·자리 부족 시간도 눌리게 열어 둠 → 누르면 서버가 409(SLOT_SOLD_OUT 등)로 막는 걸 보여 줌
            page = CLOSED_SLOT.sub(r"\1", page)
        headers = {k: v for k, v in response.headers.items() if k.lower() != "content-length"}
        return Response(page, status_code=response.status_code, headers=headers)


@app.post("/demo/logs/clear", include_in_schema=False)
async def clear_logs(back: Annotated[str, Form()] = "/ui"):
    """시연용: 로그 창 비우기 (터미널의 cls처럼). 터미널에 찍힌 로그는 그대로"""
    recent_logs.lines.clear()
    return RedirectResponse(back if back.startswith("/ui") else "/ui", status_code=303)


@app.post("/demo/switch", include_in_schema=False)
async def switch_account(
    request: Request,
    auth: Annotated[AuthService, Depends(create_auth_service)],
    who: Annotated[str, Form()],
):
    """시연용: 시드 계정으로 진짜 로그인해서 화면 로그인 쿠키를 바꿔 끼움 (시연 앱에서만 있는 주소)"""
    if who not in ACCOUNTS:
        return Response("모르는 시연 계정이에요.", status_code=404)
    name, email, password = ACCOUNTS[who]
    try:
        issued = await auth.login(email=email, password=password)
        user = await auth.authenticate(token=issued.access_token)
    except AppError:
        logger.warning("시연 계정 바꾸기 실패 401 %s", name)
        return RedirectResponse("/ui", status_code=303)
    logger.warning("시연 계정 바꾸기 → %s (%s)", name, user.role)
    response = RedirectResponse(home_url(request, user), status_code=303)
    response.set_cookie(
        COOKIE_NAME, issued.access_token, max_age=issued.expires_in,
        httponly=True, samesite="lax", path=COOKIE_PATH, secure=request.url.scheme == "https",
    )
    return response


app.add_middleware(LogPanelMiddleware)  # 마지막에 붙인 것이 가장 바깥 → 팀 로그가 먼저 찍힘

