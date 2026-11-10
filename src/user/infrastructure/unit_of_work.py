# [담당1 - 강성수]

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from common.unit_of_work import ConflictError, UnitOfWork


class SQLAlchemyUnitOfWork(UnitOfWork):
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def commit(self) -> None:
        try:
            await self.session.commit()
        except IntegrityError as e:
            await self.session.rollback()
            raise ConflictError() from e

    async def release(self) -> None:
        # 트랜잭션을 끝내면 연결이 풀로 돌아간다. 다음 쿼리는 새 트랜잭션을 연다.
        # rollback은 세션에 읽어 둔 ORM 객체를 만료시키므로, 저장소는 ORM 모델을
        # 들고 있지 말고 도메인 객체로 바꿔 돌려줘야 한다 (지금 저장소들은 그렇게 함)
        await self.session.rollback()
