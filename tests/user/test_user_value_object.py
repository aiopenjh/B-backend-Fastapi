# [담당1 - 강성수] user 도메인 VO(Email) 테스트
import dataclasses

import pytest

from common.errors import InvalidInputError
from user.domain.value_object import Email


def test_email_is_trimmed_and_lowercased():
    assert Email("  Alice@Example.COM ").value == "alice@example.com"


def test_invalid_email_raises_input_error_on_email_field():
    with pytest.raises(InvalidInputError) as exc:
        Email("not-an-email")

    assert "email" in exc.value.errors


def test_emails_differing_only_in_case_are_equal():
    assert Email("ALICE@example.com") == Email("alice@EXAMPLE.com")


def test_cannot_change_after_creation():
    email = Email("alice@example.com")

    with pytest.raises(dataclasses.FrozenInstanceError):
        email.value = "bob@example.com"  # type: ignore[misc]
