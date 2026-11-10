# [담당1 - 강성수]

from abc import ABC, abstractmethod

from common.errors import AppError


class ConflictError(AppError):
    """확정(commit)시 이미 있는 데이터와 충돌함 (유일해야 하는 값 중복)"""


class UnitOfWork(ABC):
    """유스케이스 하나의 변경을 한 번을 확정하는 포트"""

    @abstractmethod
    async def commit(self) -> None:
        """변경을 확정한다. 충돌하면 ConflictError 발생"""

    async def release(self) -> None:
        """읽기만 한 트랜잭션을 끝내 DB 연결을 돌려준다.

        비밀번호 해시처럼 오래 걸리는 작업 전에 부른다. 확정하지 않은 변경은 버려지므로
        아무것도 바꾸지 않은 상태에서만 부른다. 기본은 아무것도 하지 않는다.
        """
