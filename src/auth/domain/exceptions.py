from common.errors import UnauthorizedError


class InvalidCredentialsError(UnauthorizedError):
    """사용자 없음, 탈퇴, 비밀번호 틀림을 구분하지 않는 로그인 실패"""

    message = "이메일 또는 비밀번호가 올바르지 않습니다."
