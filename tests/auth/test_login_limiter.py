# [담당1 - 강성수] 로그인 실패 횟수 제한 테스트 (시계를 직접 움직임)
from auth.domain.limiter import LoginAttemptKey
from auth.infrastructure.login_limiter import InMemoryLoginAttemptLimiter

KEY = LoginAttemptKey(email="owner@example.com", client_ip="10.0.0.1")
WINDOW = 900.0  # 15분


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def make_limiter(
    clock: FakeClock, max_keys: int = 10_000
) -> InMemoryLoginAttemptLimiter:
    return InMemoryLoginAttemptLimiter(
        max_failures=5, window_seconds=WINDOW, max_keys=max_keys, clock=clock
    )


def attempt(limiter: InMemoryLoginAttemptLimiter, times: int, key=KEY) -> list[bool]:
    results = []
    for _ in range(times):
        reservation = limiter.try_acquire(key)
        results.append(reservation is not None)
        if reservation is not None:
            limiter.record_failure(reservation)
    return results


def test_first_five_attempts_are_allowed_then_blocked():
    limiter = make_limiter(FakeClock())

    assert attempt(limiter, 6) == [True, True, True, True, True, False]
    assert limiter.is_blocked(KEY) is True


def test_blocked_attempt_is_not_recorded():
    clock = FakeClock()
    limiter = make_limiter(clock)
    attempt(limiter, 5)
    clock.now += 600
    attempt(limiter, 10)  # 막힌 시도는 기록하지 않음 → 창이 뒤로 밀리지 않는다

    clock.now += 301  # 첫 5번이 15분 지남

    assert limiter.is_blocked(KEY) is False


def test_unblocked_after_window_passes():
    clock = FakeClock()
    limiter = make_limiter(clock)
    attempt(limiter, 5)

    clock.now += WINDOW + 1

    assert limiter.try_acquire(KEY) is not None


def test_attempts_expire_one_by_one_sliding_window():
    clock = FakeClock()
    limiter = make_limiter(clock)
    attempt(limiter, 1)  # t=1000
    clock.now += 600
    attempt(limiter, 4)  # t=1600, 합계 5 → 막힘
    assert limiter.is_blocked(KEY) is True

    clock.now += 301  # 첫 시도(t=1000)만 15분이 지남 → 4개 남음

    assert limiter.is_blocked(KEY) is False


def test_reset_clears_attempts():
    limiter = make_limiter(FakeClock())
    for _ in range(4):
        reservation = limiter.try_acquire(KEY)
        assert reservation is not None
        limiter.record_failure(reservation)
    success = limiter.try_acquire(KEY)
    assert success is not None

    limiter.reset(success)

    assert limiter.is_blocked(KEY) is False


def test_release_gives_back_one_attempt():
    # 비밀번호와 상관없는 오류(DB 장애 등)로 끝난 시도는 되돌린다
    limiter = make_limiter(FakeClock())
    reservation = limiter.try_acquire(KEY)
    assert reservation is not None
    attempt(limiter, 4)

    limiter.release(reservation)

    assert limiter.try_acquire(KEY) is not None
    assert limiter.try_acquire(KEY) is None


def test_release_removes_only_its_own_reservation():
    # 처음·마지막·유일한 대기 예약이 아닌 가운데 예약을 돌려줘도 다른 예약은 그대로여야 한다
    clock = FakeClock()
    limiter = make_limiter(clock)
    first = limiter.try_acquire(KEY)
    middle = limiter.try_acquire(KEY)
    last = limiter.try_acquire(KEY)

    limiter.release(middle)
    limiter.record_failure(first)
    limiter.record_failure(last)

    # 완료된 실패 2건만 남아 3번 더 시도할 수 있다
    assert attempt(limiter, 4) == [True, True, True, False]
    # 윈도가 지나면 모두 만료된다. 남의 예약을 지웠다면 대기 예약이 만료되지 않고 남는다
    # (만료 정리는 그 키를 조회할 때 일어나므로 한 번 조회한 뒤 센다)
    clock.now += WINDOW + 1
    assert limiter.is_blocked(KEY) is False
    assert limiter.tracked_keys() == 0


def test_keys_are_independent():
    limiter = make_limiter(FakeClock())
    other_ip = LoginAttemptKey(email="owner@example.com", client_ip="10.0.0.2")
    other_email = LoginAttemptKey(email="alice@example.com", client_ip="10.0.0.1")

    attempt(limiter, 5)

    assert limiter.is_blocked(other_ip) is False
    assert limiter.is_blocked(other_email) is False


def key(i: int) -> LoginAttemptKey:
    return LoginAttemptKey(email=f"u{i}@example.com", client_ip="1.1.1.1")


def test_expired_keys_are_dropped_when_too_many_keys():
    clock = FakeClock()
    limiter = make_limiter(clock, max_keys=3)
    for i in range(3):
        attempt(limiter, 1, key(i))

    clock.now += WINDOW + 1
    attempt(limiter, 1, key(99))

    assert limiter.tracked_keys() == 1


def test_live_keys_are_never_dropped():
    # 오래된 키를 강제로 지우면 공격자가 새 키를 쏟아 내 자기 기록을 지울 수 있다
    limiter = make_limiter(FakeClock(), max_keys=3)
    for i in range(10):
        attempt(limiter, 1, key(i))

    assert limiter.tracked_keys() == 10


def test_sweep_does_not_run_on_every_new_key():
    # 살아 있는 키가 많을 때 새 키마다 전체를 훑으면 이벤트 루프가 느려진다
    limiter = make_limiter(FakeClock(), max_keys=4)
    for i in range(32):
        attempt(limiter, 1, key(i))

    # 4 → 8 → 16 → 32 처럼 크기가 두 배가 될 때만 정리한다
    assert limiter.sweeps <= 4
