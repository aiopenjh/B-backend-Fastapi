# [담당 4] 예약 트랜잭션 시간 제한 : 락 대기·쿼리·멈춘 트랜잭션의 상한 값과, 그 시간 초과 DB 오류를 예약 에러로 바꾸는 훅
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import event
from sqlalchemy.engine import ExceptionContext
from sqlalchemy.ext.asyncio import AsyncEngine

from reservation.domain.exceptions import ReservationBusyError, ReservationTimeoutError

# PostgreSQL 오류 코드 (sqlstate). 셋 다 우리가 예약 트랜잭션에 건 시간 제한에서만 난다
LOCK_NOT_AVAILABLE = "55P03"  # 락 대기 시간(lock_timeout) 초과
QUERY_CANCELED = "57014"  # 쿼리 시간(statement_timeout) 초과
IDLE_IN_TRANSACTION_TIMEOUT = (
    "25P03"  # 멈춘 트랜잭션(idle_in_transaction_session_timeout)이라 세션 끊김
)
# (25P03은 보통 클라이언트까지 못 오고 연결만 닫힌다. 그러면 멈춘 요청은 "연결 끊김" DB 오류로 실패하고,
#  잠금이 풀리는 효과는 똑같다. 연결 끊김 전체를 바꾸면 다른 모듈의 진짜 DB 장애까지 예약 에러가 돼서 바꾸지 않는다)

ONE_MS = timedelta(milliseconds=1)


def _ms(value: timedelta) -> int:
    return int(value / ONE_MS)


@dataclass(frozen=True)
class TimeLimits:
    """예약 트랜잭션 하나에 거는 시간 상한.
    - lock: 앞 요청의 잠금을 기다리는 최대 시간 (기다리는 쪽 B)
    - statement: 쿼리 하나의 최대 시간 (잠근 쪽 A가 DB 안에서 느릴 때)
    - idle_in_transaction: 트랜잭션을 연 채 명령 없이 멈출 수 있는 최대 시간 (잠근 쪽 A가 파이썬에서 멈출 때)"""

    lock: timedelta
    statement: timedelta
    idle_in_transaction: timedelta

    def __post_init__(self) -> None:
        # PostgreSQL에서 0은 "무제한"이라 안전장치가 꺼진다. 1밀리초보다 작으면(0으로 잘림) 막는다
        for name in ("lock", "statement", "idle_in_transaction"):
            if _ms(getattr(self, name)) < 1:
                raise ValueError(f"{name}은(는) 1밀리초 이상이어야 합니다 (0은 무제한)")
        # 쿼리 제한은 락을 기다리는 시간도 포함해서 잰다. 락 대기가 먼저 끝나야 기다림이 409(잠시 후 다시)로 끝난다
        if self.lock >= self.statement:
            raise ValueError("lock은 statement보다 짧아야 합니다")

    def as_settings(self) -> dict[str, str]:
        """PostgreSQL 설정 이름 -> 값(밀리초 글자). 저장소가 set_config로 이 트랜잭션에만 건다."""
        return {
            "lock_timeout": f"{_ms(self.lock)}ms",
            "statement_timeout": f"{_ms(self.statement)}ms",
            "idle_in_transaction_session_timeout": f"{_ms(self.idle_in_transaction)}ms",
        }


# 기본값. 100명이 한 슬롯에 몰려도 1.83초 안에 끝나고 정상 최대 대기는 약 0.3초라, 정상 요청은 안 끊긴다
DEFAULT_TIME_LIMITS = TimeLimits(
    lock=timedelta(seconds=3),
    statement=timedelta(seconds=5),
    idle_in_transaction=timedelta(seconds=10),
)


def translate_time_limit_error(context: ExceptionContext) -> None:
    """DB 오류가 날 때마다 SQLAlchemy가 부른다. 시간 제한 오류만 예약 에러(AppError)로 바꾸고, 나머지는 그대로 둔다.
    AppError라서 API는 실패 봉투(409/503)로, 화면(web.py의 except AppError)은 안내로 처리된다."""
    sqlstate = getattr(context.original_exception, "sqlstate", None)
    if sqlstate == LOCK_NOT_AVAILABLE:
        raise ReservationBusyError() from context.sqlalchemy_exception
    if sqlstate in (QUERY_CANCELED, IDLE_IN_TRANSACTION_TIMEOUT):
        raise ReservationTimeoutError() from context.sqlalchemy_exception
    # 데드락(40P01) 등 다른 오류는 다른 모듈에서도 날 수 있어서 바꾸지 않는다 (엉뚱한 "예약 처리 중" 문구 방지)


def register_time_limit_errors(engine: AsyncEngine) -> None:
    """엔진에 위 훅을 단다. 여러 번 불러도 한 번만 달린다."""
    target = engine.sync_engine
    if not event.contains(target, "handle_error", translate_time_limit_error):
        event.listen(target, "handle_error", translate_time_limit_error)
