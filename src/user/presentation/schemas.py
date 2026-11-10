# [담당1 - 강성수]

import uuid
from typing import Annotated
from pydantic import BaseModel, EmailStr, Field, StringConstraints, ConfigDict

from user.domain.user import PASSWORD_MAX_LENGTH, Role, User

PHONE_REGEX = r"^01[016789]-?\d{3,4}-?\d{4}$"

MobilePhone = Annotated[
    str,
    StringConstraints(strip_whitespace=True, pattern=PHONE_REGEX),
    Field(examples=["010-1234-5678"], description="휴대폰 번호"),
]


class SignUpUserRequest(BaseModel):
    """회원가입 요청 스키마"""

    name: Annotated[
        str,
        Field(min_length=2, max_length=20, description="사용자 이름 (2~20자)"),
    ]
    email: EmailStr = Field(description="로그인에 사용할 사용자 이메일")
    password: Annotated[
        str,
        Field(
            min_length=8,
            max_length=PASSWORD_MAX_LENGTH,
            description="비밀번호 (8~72자, 영문/숫자/특수문자 포함)",
        ),
    ]
    phone: MobilePhone


class LoginUserRequest(BaseModel):
    """사용자 로그인 요청 스키마"""

    email: EmailStr = Field(description="로그인에 사용할 사용자 이메일")
    password: Annotated[
        str,
        Field(min_length=8, description="비밀번호 (8자 이상, 영문/숫자/특수문자 포함)"),
    ]


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
