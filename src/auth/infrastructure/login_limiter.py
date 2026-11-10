# [담당1 - 강성수]
import time
from collections.abc import Callable
from dataclasses import dataclass

from auth.domain.limiter import (
    LoginAttemptKey,
    LoginAttemptLimiter,
    LoginAttemptReservation,
)


@dataclass
class _Attempt:
    failed_at: float | None = None


class InMemoryLoginAttemptLimiter(LoginAttemptLimiter):
    """프로세스 메모리에 시도 시각을 보관한다 (슬라이딩 윈도).

    앱이 프로세스 1개로 돌기 때문에 충분하다. 재시작하면 초기화되고,
    프로세스를 여러 개로 늘리면 프로세스마다 따로 센다.
    각 메서드는 await 없이 끝나므로 이벤트 루프 안에서 섞이지 않는다.

    메모리: 아직 윈도 안에 있는 키는 지우지 않는다. 강제로 지우면 공격자가 새 키를
    쏟아 내 자기 기록을 밀어낼 수 있기 때문이다. 키 수는 "실패 속도 x 15분"으로
    제한되고, 실패 속도는 bcrypt 처리량(초당 수십 번)에 묶여 있다.
    """

    def __init__(
        self,
        max_failures: int = 5,
        window_seconds: float = 15 * 60,
        max_keys: int = 10_000,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.max_failures = max_failures
        self.window_seconds = window_seconds
        self.max_keys = max_keys
        self.clock = clock
        self.sweeps = 0
        self._sweep_at = max_keys
        self._attempts: dict[
            LoginAttemptKey, dict[LoginAttemptReservation, _Attempt]
        ] = {}

    def try_acquire(self, key: LoginAttemptKey) -> LoginAttemptReservation | None:
        attempts = self._recent(key)
        if attempts is not None and len(attempts) >= self.max_failures:
            return None
        if attempts is None:
            self._maybe_sweep()
            attempts = self._attempts[key] = {}
        reservation = LoginAttemptReservation(key)
        attempts[reservation] = _Attempt()
        return reservation

    def release(self, reservation: LoginAttemptReservation) -> None:
        attempts = self._attempts.get(reservation.key)
        if attempts is not None:
            attempts.pop(reservation, None)
            if not attempts:
                del self._attempts[reservation.key]

    def record_failure(self, reservation: LoginAttemptReservation) -> None:
        attempts = self._recent(reservation.key)
        if attempts is not None and reservation in attempts:
            attempts[reservation].failed_at = self.clock()

    def reset(self, reservation: LoginAttemptReservation) -> None:
        attempts = self._recent(reservation.key)
        if attempts is None or reservation not in attempts:
            return
        # 다른 요청은 성공 뒤에도 완료 전까지 한도를 차지한다.
        pending = {
            handle: attempt
            for handle, attempt in attempts.items()
            if handle is not reservation and attempt.failed_at is None
        }
        if pending:
            self._attempts[reservation.key] = pending
        else:
            del self._attempts[reservation.key]

    def is_blocked(self, key: LoginAttemptKey) -> bool:
        attempts = self._recent(key)
        return attempts is not None and len(attempts) >= self.max_failures

    def tracked_keys(self) -> int:
        return len(self._attempts)

    def _recent(
        self, key: LoginAttemptKey
    ) -> dict[LoginAttemptReservation, _Attempt] | None:
        """윈도를 지난 시도를 버리고 남은 시도를 돌려준다. 하나도 없으면 키를 지운다"""
        attempts = self._attempts.get(key)
        if attempts is None:
            return None
        cutoff = self.clock() - self.window_seconds
        for handle, attempt in list(attempts.items()):
            if attempt.failed_at is not None and attempt.failed_at <= cutoff:
                del attempts[handle]
        if not attempts:
            del self._attempts[key]
            return None
        return attempts

    def _maybe_sweep(self) -> None:
        # 전체를 훑는 건 O(키 수)라, 키 수가 지난번 정리 때의 두 배가 됐을 때만 한다.
        # 새 키마다 훑으면 키가 많을 때 이벤트 루프가 느려진다
        if len(self._attempts) < self._sweep_at:
            return
        for key in list(self._attempts):
            self._recent(key)
        self.sweeps += 1
        self._sweep_at = max(self.max_keys, 2 * len(self._attempts))
