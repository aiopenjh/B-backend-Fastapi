# [담당1 - 강성수]

import uuid
from typing import Annotated
from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
)

from common.errors import InvalidInputError
from user.domain.user import PASSWORD_MAX_LENGTH, Role, User
from user.domain.value_object import EMAIL_ERROR_MESSAGE, Email

PHONE_REGEX = r"^01[016789]-?\d{3,4}-?\d{4}$"

MobilePhone = Annotated[
    str,
    StringConstraints(strip_whitespace=True, pattern=PHONE_REGEX),
    Field(examples=["010-1234-5678"], description="휴대폰 번호"),
]


def _check_service_email(value: str) -> str:
    """도메인 Email과 같은 규칙으로 검사한다.

    EmailStr(표준 검사기)는 o'neil@example.com 같은 주소도 받아서, 스키마를 통과한 값이
    서비스에서 다시 거절됐다. 정규화는 서비스가 Email로 하므로 값은 그대로 돌려준다.
    """
    try:
        Email(value)
    except InvalidInputError:
        raise ValueError(EMAIL_ERROR_MESSAGE) from None
    return value


ServiceEmail = Annotated[
    str,
    AfterValidator(_check_service_email),
    Field(
        examples=["alice@example.com"],
        description="로그인에 사용할 이메일 (영문·숫자·. _ % + - 만 사용)",
        json_schema_extra={"format": "email"},
    ),
]


class SignUpUserRequest(BaseModel):
    """회원가입 요청 스키마"""

    name: Annotated[
        str,
        Field(min_length=2, max_length=20, description="사용자 이름 (2~20자)"),
    ]
    email: ServiceEmail
    password: Annotated[
        str,
        Field(
            min_length=8,
            max_length=PASSWORD_MAX_LENGTH,
            description="비밀번호 (8~72자, 영문·숫자·특수문자 포함, 특수문자는 영문 자판 기호이며 공백 제외)",
        ),
    ]
    phone: MobilePhone


class UserResponse(BaseModel):
    """사용자 정보 응답 스키마"""

    model_config = ConfigDict(from_attributes=True)

    id: Annotated[uuid.UUID, Field(description="사용자 고유 ID")]
    email: Annotated[str, Field(description="이메일")]
    name: Annotated[str, Field(description="사용자 이름")]
    phone: Annotated[str, Field(description="휴대폰 번호")]
    role: Annotated[Role, Field(description="사용자 역할")]

    @classmethod
    def from_domain(cls, user: User) -> "UserResponse":
        """도메인 User -> 응답 DTO. Email VO는 문자열로 꺼낸다"""
        return cls(
            id=user.id,
            email=user.email.value,
            name=user.name,
            phone=user.phone,
            role=user.role,
        )
