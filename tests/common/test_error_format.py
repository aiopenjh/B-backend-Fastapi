# """[담당2] 에러 형식 확인용 임시 테스트

# - API_SPEC.md의 실패 예시와 같은 요청
# - 구현 가이드(교안)가 쓰는 방식 그대로 예외를 던졌을 때도 팀 공통 형식으로 나가는지
# """

# from typing import Literal

# from fastapi import FastAPI, HTTPException, Query, Request
# from fastapi.testclient import TestClient
# from pydantic import BaseModel, Field, model_validator

# from common.error_handlers import register_exception_handlers
# from common.errors import (
#     BadRequestException,
#     ConflictException,
#     ForbiddenException,
#     NotFoundException,
#     ServiceUnavailableException,
#     UnauthorizedException,
#     ValidationException,
# )


# class RestaurantUpdate(BaseModel):
#     name: str | None = Field(default=None, min_length=1, max_length=150)
#     phone: str | None = None

#     @model_validator(mode="after")
#     def at_least_one(self):
#         if not self.model_fields_set:
#             raise ValueError("수정할 필드를 하나 이상 보내야 합니다.")
#         return self


# app = FastAPI()
# register_exception_handlers(app)


# @app.middleware("http")
# async def fake_request_id(request: Request, call_next): #담당 1의 미들웨어 흉내
#     if request.headers.get("x-test-id"):
#         request.state.request_id = request.headers["x-test-id"]
#     return await call_next(request)


# @app.get("/restaurants")
# async def list_restaurants(
#     page_size: int = Query(20, ge=1, le=100),
#     sort: Literal["id", "name", "newest"] = "id",
# ):
#     return {"ok": True}


# @app.get("/restaurants/{restaurant_id}")
# async def get_restaurant(restaurant_id: int):
#     if restaurant_id == 999:
#         raise NotFoundException("식당을 찾을 수 없습니다.")
#     return {"id": restaurant_id}


# @app.patch("/owner/restaurants/{restaurant_id}")
# async def patch_restaurant(restaurant_id: int, body: RestaurantUpdate):
#     if restaurant_id == 3:
#         raise ForbiddenException("본인의 식당만 수정할 수 있습니다.")
#     return {"id": restaurant_id}


# # ---- 교안 (User/Auth 페이지)이 쓰는 방식 그대로 던져보기 ----
# @app.get("/guide/login-fail")
# async def login_fail():
#     raise UnauthorizedException("이메일 또는 비밀번호가 올바르지 않습니다.")


# @app.get("/guide/withdrawn")
# async def withdrawn():
#     raise ForbiddenException(
#         message="탈퇴한 회원은 서비스를 이용할 수 없습니다.",
#         error_code="USER_ALREADY_WITHDRAWN",
#     )


# @app.get("/guide/email-exists")
# async def email_exists():
#     raise ConflictException(
#         message="이미 사용 중인 이메일입니다.", error_code="EMAIL_ALREADY_EXISTS"
#     )


# @app.get("/guide/bad-email")
# async def bad_email():
#     raise ValidationException(
#         message="유효하지 않은 이메일 형식입니다.",
#         field_errors={"email": ["올바른 이메일 형식을 입력하세요."]},
#     )


# @app.get("/guide/old-password")
# async def old_password():
#     raise BadRequestException(
#         message="기존 비밀번호가 일치하지 않습니다.", error_code="INVALID_OLD_PASSWORD"
#     )


# @app.get("/guide/user-not-found")
# async def user_not_found():
#     raise NotFoundException(
#         message="사용자를 찾을 수 없습니다.", error_code="USER_NOT_FOUND"
#     )


# # ---- API_SPEC의 409 예시 (details 포함) / 503 ----
# @app.get("/boom/sold-out")
# async def sold_out():
#     raise ConflictException(
#         message="남은 자리가 부족합니다.",
#         error_code="SLOT_SOLD_OUT",
#         errors={"remaining": 2, "requested": 3},
#     )


# @app.get("/boom/db")
# async def boom_db():
#     raise ServiceUnavailableException()


# @app.get("/boom/db-old-style")
# async def boom_db_old_style():
#     raise HTTPException(status_code=503, detail="요청하신 서비스가 잠시 내부적으로 문제가 발생했습니다.")


# @app.get("/boom/auth")
# async def boom_auth():
#     raise HTTPException(status_code=401, detail="Not authenticated", headers={"WWW-Authenticate": "Bearer"})


# @app.get("/boom/unhandled")
# async def boom_unhandled():
#     raise RuntimeError("비밀 내부 정보")


# client = TestClient(app, raise_server_exceptions=False)


# def check_shape(body: dict):
#     assert set(body) == {"error"}
#     assert set(body["error"]) == {"code", "message", "details", "request_id"}
#     assert body["error"]["request_id"].startswith("req_")


# def error_of(response) -> dict:
#     check_shape(response.json())
#     return response.json()["error"]


# # ----------------------------- API_SPEC 실패 예시 --------------------------------
# def test_404_not_found():
#     r = client.get("/restaurants/999")
#     assert r.status_code == 404
#     e = error_of(r)
#     assert (e["code"], e["message"], e["details"]) == ("NOT_FOUND", "식당을 찾을 수 없습니다.", {})


# def test_422_page_size_too_big__and__small():
#     r = client.get("/restaurants?page_size=500")
#     assert r.status_code == 422
#     assert error_of(r)["code"] == "VALIDATION_ERROR"
#     assert error_of(r)["details"] == {"page_size": "100 이하여야 합니다."}
#     r = client.get("/restaurants?page_size=0")
#     assert error_of(r)["details"] == {"page_size": "1 이상이어야 합니다."}


# def test_422_sort_literal():
#     r = client.get("/restaurants?sort=price")
#     assert r.status_code == 422
#     assert error_of(r)["details"] == {"sort": "id, name, newest 중 하나여야 합니다."}


# def test_422_path_not_int():
#     r = client.get("/restaurants/abc")
#     assert r.status_code == 422
#     assert error_of(r)["details"] == {"restaurant_id": "정수여야 합니다."}


# def test_422_body_custom_rule_and_length():
#     r = client.patch("/owner/restaurants/1", json={})
#     assert error_of(r)["details"] == {"body": "수정할 필드를 하나 이상 보내야 합니다."}
#     r = client.patch("/owner/restaurants/1", json={"name": ""})
#     assert error_of(r)["details"] == {"name": "1자 이상이어야 합니다."}
#     r = client.patch("/owner/restaurants/1", json={"name": "가" * 151})
#     assert error_of(r)["details"] == {"name": "150자 이하여야 합니다."}


# def test_422_body_not_json():
#     r = client.patch("/owner/restaurants/1", content="not json", headers={"content-type": "application/json"})
#     assert r.status_code == 422
#     check_shape(r.json())


# def test_403_forbidden_not_my_restaurant():
#     r = client.patch("/owner/restaurants/3", json={"phone": "02-1"})
#     assert r.status_code == 403
#     e = error_of(r)
#     assert (e["code"], e["message"]) == ("FORBIDDEN", "본인의 식당만 수정할 수 있습니다.")


# # def test_409_sold_out_with_details():
# #     r = client.get("/boom/sold-out")
# #     assert r.status_code == 409

    