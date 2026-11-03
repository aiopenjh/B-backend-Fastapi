from http import HTTPStatus

from common.errors import CommonErrorCode


def test_error_code_exposes_status_code_and_message():
    error_code = CommonErrorCode.NOT_FOUND

    assert error_code.status == HTTPStatus.NOT_FOUND
    assert error_code.code == "NOT_FOUND"
    assert error_code.message
