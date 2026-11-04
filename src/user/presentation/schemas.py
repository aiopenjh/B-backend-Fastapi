import uuid
from typing import Annotated
from pydantic import BaseModel, EmailStr, Field, StringConstraints, ConfigDict

from user.domain.user import Role

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
        Field(min_length=2, max_length=8, description="로그인에 사용할 사용자 이름"),
    ]
    email: EmailStr = Field(description="로그인에 사용할 사용자 이메일")
    row_password: Annotated[
        str,
        Field(min_length=8, description="비밀번호 (8자 이상, 영문/숫자/특수문자 포함)"),
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
