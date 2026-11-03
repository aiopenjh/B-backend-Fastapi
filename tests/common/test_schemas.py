import os
import subprocess
import sys
from datetime import timedelta

from common.errors import CommonErrorCode
from common.schemas import APIResponse


def test_ok_wraps_data_in_success_envelope():
    response = APIResponse.ok({"id": 1})

    assert response.success is True
    assert response.code == "OK"
    assert response.errors is None
    assert response.data == {"id": 1}


def test_fail_takes_code_and_message_from_error_code():
    response = APIResponse.fail(CommonErrorCode.UNAUTHORIZED)

    assert response.success is False
    assert response.code == "UNAUTHORIZED"
    assert response.message == CommonErrorCode.UNAUTHORIZED.message
    assert response.errors == {}
    assert response.data is None


def test_fail_keeps_given_message_and_field_errors():
    errors = {"party_size": ["1 이상이어야 합니다."]}

    response = APIResponse.fail(
        CommonErrorCode.VALIDATION_ERROR, message="입력 확인", errors=errors
    )

    assert response.message == "입력 확인"
    assert response.errors == errors


def test_responded_at_uses_seoul_offset():
    response = APIResponse.ok()

    assert response.responded_at.utcoffset() == timedelta(hours=9)


def test_request_id_is_none_outside_request():
    assert APIResponse.ok().request_id is None


def test_schemas_import_without_system_timezone_database():
    # Windows처럼 시스템 시간대 DB가 없는 환경을 PYTHONTZPATH=""로 흉내 냄
    env = {**os.environ, "PYTHONTZPATH": "", "PYTHONPATH": "src"}

    result = subprocess.run(
        [sys.executable, "-c", "import common.schemas"],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
