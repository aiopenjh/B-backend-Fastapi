# [담당 4] 예약 값 객체 테스트 : 연락처(휴대폰 번호) 검사와 모양 맞추기, 행동하는 사람(Actor)
import dataclasses
import uuid
from datetime import datetime

import pytest

from auth.domain.value_object import AuthenticatedUser, AuthRole
from common.errors import InvalidInputError
from common.schemas import SEOUL
from reservation.domain.reservation import Reservation
from reservation.domain.value_object import Actor, ActorRole, ContactPhone

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


# 역할 글자("OWNER" 등)를 받아 예약 쪽 역할(ActorRole)로 바꿔 둔다
@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("CUSTOMER", ActorRole.CUSTOMER),
        ("OWNER", ActorRole.OWNER),
        ("ADMIN", ActorRole.ADMIN),
    ],
)
def test_actor_converts_role(raw, expected):
    actor = Actor(USER_ID, raw)
    # 글자로 넣어도 Enum으로 바뀌어 있어야 한다 (is라서 진짜 ActorRole 멤버인지까지 본다)
    assert actor.role is expected


# 모르는 역할이면 만들 수 없다 (소문자, 빈 글자, 글자가 아닌 값도 안 된다)
@pytest.mark.parametrize("raw", ["BOSS", "", "owner", None, 1])
def test_actor_rejects_unknown_role(raw):
    with pytest.raises(ValueError):
        Actor(USER_ID, raw)


# 로그인 쪽 AuthenticatedUser 값을 그대로 넣어도 된다 (입구에서 한 줄로 바꿔 끼우는 방법)
@pytest.mark.parametrize("role", list(AuthRole))
def test_actor_from_authenticated_user(role):
    user = AuthenticatedUser(user_id=USER_ID, role=role)
    actor = Actor(user.user_id, user.role)
    # 역할 이름이 같은 ActorRole로 바뀌고, user_id는 그대로다
    assert actor.role is ActorRole(role.value)
    assert actor.user_id == USER_ID


# 역할 확인 : 운영자면 is_owner만, 관리자면 is_admin만, 손님이면 둘 다 False
@pytest.mark.parametrize(
    ("role", "owner", "admin"),
    [
        (ActorRole.OWNER, True, False),
        (ActorRole.ADMIN, False, True),
        (ActorRole.CUSTOMER, False, False),
    ],
)
def test_actor_role_checks(role, owner, admin):
    actor = Actor(USER_ID, role)
    assert actor.is_owner() is owner
    assert actor.is_admin() is admin


# 값 객체 : 값이 같으면 같은 것으로 보고, 만든 뒤에는 못 바꾼다
def test_actor_is_value_object():
    actor = Actor(USER_ID, ActorRole.OWNER)
    # 값이 같으면 같은 것으로 본다 (Enum으로 바뀌는지는 test_actor_converts_role이 is로 확인)
    assert actor == Actor(USER_ID, "OWNER")
    assert actor != Actor(USER_ID, ActorRole.ADMIN)
    with pytest.raises(dataclasses.FrozenInstanceError):
        actor.role = ActorRole.ADMIN
