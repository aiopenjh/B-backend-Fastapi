# [담당1 - 강성수]

from typing import Annotated

from fastapi import APIRouter, Depends, Request, status
from common.schemas import APIResponse

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/login",
    response_model=APIResponse,
    status_code=status.HTTP_200_OK,
    description="로그인 완료",
)
async def login():
    pass
