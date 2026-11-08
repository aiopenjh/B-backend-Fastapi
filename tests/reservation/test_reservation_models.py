# [담당 4] 예약 모델 테스트 : DB가 지키는 마지막 규칙 확인
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateIndex

from reservation.infrastructure.models import ReservationModel

def test_confirmed_reservation_is_uniqu_per_user_and_slot():
    # 같은 사람, 같은 슬롯의 확정 예약은 하나만 (취소된 예약은 여러개여도 된다.)
    index = next(
        i for i in ReservationModel.__table__.indexes
        if i.name == "uq_reservations_user_slot_confirmed"
    )

    sql = str(CreateIndex(index).compile(dialect=postgresql.dialect()))

    assert index.unique  is True
    assert "(user_id, slot_id)" in sql
    assert "WHERE status = 'CONFIRMED'" in sql