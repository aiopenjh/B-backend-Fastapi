# [담당1-강성수]

import re
from dataclasses import dataclass
from common.errors import InvalidInputError

EMAIL_REGEX = re.compile(r"^[\w\.-]+@[\w\.-]+\.\w+$")


@dataclass(frozen=True)
class Email:
    value: str

    def __post_init__(self) -> None:
        """공백 제거, 소문자 정규화 형식 검증을 통과한 이메일"""

        # self.value = 대입이 막혀 있어 object.__setattr__로 진행
        object.__setattr__(self, "value", self.value.strip().lower())
        self._validate()

    def _validate(self) -> None:
        if not EMAIL_REGEX.match(self.value):
            raise InvalidInputError(
                errors={"email": ["올바른 이메일 형식이 아닙니다."]}
            )
