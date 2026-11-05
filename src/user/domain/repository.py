# [담당1 - 강성수]

import uuid
from abc import ABC, abstractmethod
from user.domain.user import User
from user.domain.value_object import Email


class UserRepository(ABC):

    @abstractmethod
    async def find_by_id(self, user_id: uuid.UUID) -> User | None:
        """ID 기준으로 사용자 단건 조회"""
        pass

    @abstractmethod
    async def find_by_email(self, email: Email) -> User | None:
        """이메일 기준으로 사용자 단건 조회"""
        pass

    @abstractmethod
    async def save(self, user: User) -> User:
        """사용자 신규 생성 또는 변경 사항 갱신"""
        pass
