from typing import Annotated, Literal

from pydantic import BaseModel, Field


class TokenResponse(BaseModel):
    """OAuth2 표준 토큰 응답. 봉투(APIResponse) 없이 최상위로 내보낸다"""

    access_token: Annotated[str, Field(description="Bearer 액세스 토큰")]
    token_type: Annotated[Literal["bearer"], Field(description="항상 bearer")] = (
        "bearer"
    )
    expires_in: Annotated[int, Field(description="만료까지 남은 초")]
