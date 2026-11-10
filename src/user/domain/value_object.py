# [담당1-강성수]

import re
from dataclasses import dataclass
from common.errors import InvalidInputError

# 서비스가 받는 이메일. 표준(RFC 5322)보다 좁은 실용적 범위이고 ASCII만 받는다.
# - 로컬 부분(@ 앞): 영문·숫자·. _ % + - (점은 처음·끝·연속 불가)
# - 도메인(@ 뒤): 영문·숫자·하이픈으로 된 이름을 점으로 잇고, 최상위 도메인은 영문 2자 이상
# 가입 스키마도 이 규칙을 그대로 쓴다 (user.presentation.schemas)
EMAIL_REGEX = re.compile(
    r"[A-Za-z0-9_%+-]+(?:\.[A-Za-z0-9_%+-]+)*"
    r"@(?:[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?\.)+[A-Za-z]{2,}"
)
EMAIL_ERROR_MESSAGE = "올바른 이메일 형식이 아닙니다."
# 길이 한도 (RFC 5321). 전체 254자는 DB 컬럼(255자) 안에 들어간다
EMAIL_MAX_LENGTH = 254
EMAIL_LOCAL_MAX_LENGTH = 64
EMAIL_DOMAIN_LABEL_MAX_LENGTH = 63


@dataclass(frozen=True)
class Email:
    value: str

    def __post_init__(self) -> None:
        """공백 제거, 소문자 정규화 형식 검증을 통과한 이메일"""

        # self.value = 대입이 막혀 있어 object.__setattr__로 진행
        object.__setattr__(self, "value", self.value.strip().lower())
        self._validate()

    def _validate(self) -> None:
        # 길이를 먼저 본다. 아주 긴 입력은 정규식까지 가지 않고, DB 컬럼 초과(500)도 막는다
        if len(self.value) > EMAIL_MAX_LENGTH or not EMAIL_REGEX.fullmatch(self.value):
            raise InvalidInputError(errors={"email": [EMAIL_ERROR_MESSAGE]})
        local, domain = self.value.split("@")
        if len(local) > EMAIL_LOCAL_MAX_LENGTH or any(
            len(label) > EMAIL_DOMAIN_LABEL_MAX_LENGTH for label in domain.split(".")
        ):
            raise InvalidInputError(errors={"email": [EMAIL_ERROR_MESSAGE]})
