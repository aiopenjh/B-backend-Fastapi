# [담당1 - 강성수]
from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class LoginAttemptKey:
    """실패 횟수를 세는 단위. 같은 IP에서 같은 계정을 계속 틀리는 경우만 막는다.

    이메일만으로 세면 공격자가 일부러 틀려서 남의 계정을 잠글 수 있다.
    """

    email: str
    client_ip: str | None


@dataclass(frozen=True, eq=False)
class LoginAttemptReservation:
    """같은 이메일+IP 안에서도 요청마다 별도로 돌려주는 예약 핸들."""

    key: LoginAttemptKey


class LoginAttemptLimiter(ABC):
    """로그인 시도 횟수 제한 포트.

    확인과 기록을 try_acquire 한 번에 한다. 확인만 하고 비밀번호 검증(await)이
    끝난 뒤 기록하면, 그사이 동시에 들어온 요청이 모두 확인을 통과해 제한이 뚫린다.
    """

    @abstractmethod
    def try_acquire(self, key: LoginAttemptKey) -> LoginAttemptReservation | None:
        """막혀 있으면 None. 아니면 이 요청만의 예약을 기록하고 반환한다."""

    @abstractmethod
    def release(self, reservation: LoginAttemptReservation) -> None:
        """비밀번호와 상관없는 오류로 끝난 요청의 예약만 되돌린다."""

    @abstractmethod
    def record_failure(self, reservation: LoginAttemptReservation) -> None:
        """해당 예약을 완료된 자격 증명 실패로 기록한다."""

    @abstractmethod
    def reset(self, reservation: LoginAttemptReservation) -> None:
        """성공한 예약과 완료된 실패를 지우고 다른 대기 중 예약은 남긴다."""

    @abstractmethod
    def is_blocked(self, key: LoginAttemptKey) -> bool:
        """지금 시도할 수 없으면 True (기록하지 않음)"""
