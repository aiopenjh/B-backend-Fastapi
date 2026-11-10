# [담당 4] 예약 값 객체 테스트 : 연락처(휴대폰 번호) 검사와 모양 맞추기
import uuid
from datetime import datetime

import pytest

from common.errors import InvalidInputError
from common.schemas import SEOUL
from reservation.domain.reservation import Reservation
from reservation.domain.value_object import ContactPhone

NOW = datetime(2026, 11, 3, 6, 0, tzinfo=SEOUL)
USER_ID = uuid.UUID("00000000-0000-4000-8000-000000000001")


# 하이픈은 있어도 없어도 받고, 항상 010-1234-5678 모양으로 맞춘다
@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("010-1234-5678", "010-1234-5678"),
        ("01012345678", "010-1234-5678"),
        ("010-12345678", "010-1234-5678"),
        ("0101234-5678", "010-1234-5678"),
        ("  01012345678  ", "010-1234-5678"),
        ("0111234567", "011-123-4567"),
        ("019-1234-5678", "019-1234-5678"),
    ],
)
def test_contact_phone_formats_mobile_number(raw, expected):
    assert ContactPhone(raw).value == expected


# 휴대폰 번호 모양이 아니면 422 (글자, NUL, 다른 나라 숫자, 일반 전화, 010인데 가운데 3자리)
@pytest.mark.parametrize(
    "raw",
    [
        "abc",
        "",
        "010\x001234",
        "010-١٢٣٤-٥٦٧٨",
        "02-123-4567",
        "0101234567",
        "010 1234 5678",
        "010--1234-5678",
    ],
)
def test_contact_phone_rejects_non_mobile(raw):
    with pytest.raises(InvalidInputError):
        ContactPhone(raw)


# 예약을 만들 때도 같은 규칙으로 연락처 모양을 맞춘다 (API가 아닌 길로 들어와도 같다)
def test_reservation_create_formats_contact_phone():
    reservation = Reservation.create(
        user_id=USER_ID, slot_id=7, party_size=2, now=NOW, contact_phone="01012345678"
    )

    assert reservation.contact_phone == "010-1234-5678"


# 예약을 만들 때 연락처가 비어 있으면 안 보낸 것(None)으로 본다
@pytest.mark.parametrize("raw", [None, "", "   "])
def test_reservation_create_blank_contact_phone_becomes_none(raw):
    reservation = Reservation.create(
        user_id=USER_ID, slot_id=7, party_size=2, now=NOW, contact_phone=raw
    )

    assert reservation.contact_phone is None


# 예약을 만들 때 모양이 틀리거나 글자가 아닌 연락처면 422
@pytest.mark.parametrize("raw", ["abc", 12345678901])
def test_reservation_create_rejects_bad_contact_phone(raw):
    with pytest.raises(InvalidInputError):
        Reservation.create(
            user_id=USER_ID, slot_id=7, party_size=2, now=NOW, contact_phone=raw
        )
