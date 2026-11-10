from enum import unique
from http import HTTPStatus

from common.errors import AppError, ErrorCode


@unique
class RestaurantErrorCode(ErrorCode):
    RESTAURANT_NOT_FOUND = (HTTPStatus.NOT_FOUND, "식당을 찾을 수 없습니다.")
    NOT_RESTAURANT_OWNER = (HTTPStatus.FORBIDDEN, "본인의 식당만 수정할 수 있습니다.")
    MENU_NOT_FOUND = (HTTPStatus.NOT_FOUND, "메뉴를 찾을 수 없습니다.")


class RestaurantNotFoundError(AppError):
    error_code = RestaurantErrorCode.RESTAURANT_NOT_FOUND


class NotRestaurantOwnerError(AppError):
    error_code = RestaurantErrorCode.NOT_RESTAURANT_OWNER


class MenuNotFoundError(AppError):
    error_code = RestaurantErrorCode.MENU_NOT_FOUND
