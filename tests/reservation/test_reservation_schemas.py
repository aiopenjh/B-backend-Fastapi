# [담당 4] 예약 응답 스키마 테스트 : API 명세 예시 검증
from reservation.presentation.schemas import ReservationOut

SPEC_EXAMPLE = {
    "id": 15,
    "user_id": "00000000-0000-4000-8000-000000000001",
    "slot_id": 7,
    "restaurant_id": 1,
    "starts_at": "2026-10-30T18:00:00+09:00",
    "ends_at": "2026-10-30T19:00:00+09:00",
    "party_size": 2,
    "contact_phone": "010-1234-5678",
    "status": "CONFIRMED",
    "created_at": "2026-10-28T15:20:00+09:00",
    "cancelled_at": None,
    "can_cancel": "True"
}

def test_reservation_out_accepts_spec_example():
    reservation = ReservationOut(**SPEC_EXAMPLE)

    assert reservation.id == 15
    assert reservation.status == "CONFIRMED"
    assert reservation.cancelled_at is None
    