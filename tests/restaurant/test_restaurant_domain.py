import uuid
from datetime import UTC, datetime

from auth.domain.value_object import AuthenticatedUser, AuthRole
from restaurant.domain.restaurant import Menu, Restaurant

OWNER_ID = uuid.uuid4()


def make_restaurant(**changes) -> Restaurant:
    """테스트용 식당. 바꾸고 싶은 값만 넘기면 나머지는 기본값"""
    base = {
        "id": 1,
        "owner_id": OWNER_ID,
        "name": "테스트 식당",
        "address": "서울시 중구",
        "cuisine": "KOREAN",
    }
    base.update(changes)
    return Restaurant(**base)


def test_is_owned_by_returns_true_for_owner():
    restaurant = make_restaurant()

    assert restaurant.is_owned_by(OWNER_ID) is True


def test_is_owned_by_returns_false_for_other_user():
    restaurant = make_restaurant()

    assert restaurant.is_owned_by(uuid.uuid4()) is False


def test_is_active_when_not_deleted():
    restaurant = make_restaurant()

    assert restaurant.is_active() is True


def test_is_not_active_when_deleted():
    restaurant = make_restaurant(deleted_at=datetime(2026, 11, 5, tzinfo=UTC))

    assert restaurant.is_active() is False


def test_menus_are_not_shared_between_restaurants():
    first = make_restaurant()
    second = make_restaurant(id=2)
    first.menus.append(Menu(id=1, name="비빔밥", price=9000))

    assert second.menus == []


def test_admin_can_edit_any_restaurant():
    restaurant = make_restaurant()
    admin = AuthenticatedUser(user_id=uuid.uuid4(), role=AuthRole.ADMIN)

    assert restaurant.can_be_edited_by(admin) is True


def test_owner_can_edit_own_restaurant():
    restaurant = make_restaurant()
    owner = AuthenticatedUser(user_id=OWNER_ID, role=AuthRole.OWNER)

    assert restaurant.can_be_edited_by(owner) is True


def test_owner_cannot_edit_other_restaurant():
    restaurant = make_restaurant()
    other_owner = AuthenticatedUser(user_id=uuid.uuid4(), role=AuthRole.OWNER)

    assert restaurant.can_be_edited_by(other_owner) is False


def test_customer_cannot_edit_restaurant():
    restaurant = make_restaurant()
    customer = AuthenticatedUser(user_id=uuid.uuid4(), role=AuthRole.CUSTOMER)

    assert restaurant.can_be_edited_by(customer) is False
