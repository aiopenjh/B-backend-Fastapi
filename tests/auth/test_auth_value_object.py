# [담당1 - 강성수] auth 도메인 VO(AuthenticatedUser) 테스트
import dataclasses
import uuid

import pytest

from auth.domain.value_object import AuthenticatedUser, AuthRole


def test_owner_is_owner_not_customer():
    user = AuthenticatedUser(user_id=uuid.uuid4(), role=AuthRole.OWNER)

    assert user.is_owner() is True
    assert user.is_customer() is False


def test_customer_is_customer_not_owner():
    user = AuthenticatedUser(user_id=uuid.uuid4(), role=AuthRole.CUSTOMER)

    assert user.is_customer() is True
    assert user.is_owner() is False


def test_same_id_and_role_are_equal():
    user_id = uuid.uuid4()

    assert AuthenticatedUser(user_id, AuthRole.OWNER) == AuthenticatedUser(
        user_id, AuthRole.OWNER
    )


def test_cannot_change_after_creation():
    user = AuthenticatedUser(user_id=uuid.uuid4(), role=AuthRole.CUSTOMER)

    with pytest.raises(dataclasses.FrozenInstanceError):
        user.role = AuthRole.OWNER  # type: ignore[misc]
