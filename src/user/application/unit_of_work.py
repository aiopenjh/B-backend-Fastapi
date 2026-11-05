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
