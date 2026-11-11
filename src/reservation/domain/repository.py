# [담당 4] 예약 창고 메뉴판 : 예약을 저장하고 꺼내는 기능의 약속(인터페이스)
import uuid
from abc import ABC, abstractmethod
from datetime import datetime, timedelta

from reservation.domain.reservation import Reservation


class ReservationRepository(ABC):
    """예약 저장소 약속. 서비스는 이것만 보고, 실제 DB구현은 infrastructure의 SQLAlchemyReservationRepository."""

    @abstractmethod
    async def set_time_limits(self) -> None:
        """예약 생성·취소·입장 확인 : 잠그기 전에 이 트랜잭션에만 시간 상한(락 대기·쿼리·멈춤)을 건다. 값은 구현이 정한다"""

    @abstractmethod
    async def exists_confirmed(self, user_id: uuid.UUID, slot_id: int) -> bool:
        """예약 생성 : 이 사용자가 이 슬롯에 CONFIRMED 예약이 있으면 True (중복 예약 확인)"""

    @abstractmethod
    async def add(self, reservation: Reservation) -> Reservation:
        """예약 생성 : 새 예약을 넣고, DB가 정한 id가 채워진 예약을 돌려줌. 같은 사람·슬롯의 확정 예약이 이미 있으면 ConflictError"""

    @abstractmethod
    async def get(self, reservation_id: int) -> Reservation | None:
        """예약 취소 : id로 예약 하나 조회. 없으면 None"""

    @abstractmethod
    async def get_for_update(self, reservation_id: int) -> Reservation | None:
        """예약 취소 : id로 예약을 잠그고 조회. 없으면 None (두 번 취소 막기)"""

    @abstractmethod
    async def save(self, reservation: Reservation) -> None:
        """예약 취소·입장 확인 : 바뀐 상태(status, cancelled_at, 누가·왜·메모, checked_in_at)를 DB에 반영"""

    @abstractmethod
    async def restaurant_owner_of(self, reservation_id: int) -> uuid.UUID | None:
        """운영자 취소·입장 확인 : 이 예약이 속한 식당(삭제 안 된 것)의 주인 id. 없으면 None"""

    @abstractmethod
    async def list_no_show_ids(self, now: datetime, grace: timedelta) -> list[int]:
        """자동 노쇼 : 확정 + 입장 안 함 + 시작 후 유예 시간이 지난 예약 번호들"""
