from restaurant.infrastructure.seed import parse_row

ROW = {
    "name": "들꽃분식집",
    "description": "종로구 낙원동의 분식 전문점",
    "address": "서울특별시 종로구 수표로 146 (낙원동)",
    "cuisine": "BUNSIK",
    "image_url": "",
    "phone": "02-0000-0001",
    "email": "owner00001@example.com",
    "menu1": "김밥",
    "menu1_price": "2500",
    "menu2": "라볶이",
    "menu2_price": "5500",
    "menu3": "튀김 모둠",
    "menu3_price": "3500",
}


def test_parse_row_makes_owner_from_email_name_phone():
    owner, _, _ = parse_row(ROW)

    assert owner == {
        "email": "owner00001@example.com",
        "name": "들꽃분식집",
        "phone": "02-0000-0001",
    }


def test_parse_row_turns_empty_image_url_into_none():
    _, restaurant, _ = parse_row(ROW)

    assert restaurant["image_url"] is None
    assert restaurant["name"] == "들꽃분식집"
    assert restaurant["cuisine"] == "BUNSIK"


def test_parse_row_makes_three_menus_with_int_price():
    _, _, menus = parse_row(ROW)

    assert menus == [
        {"name": "김밥", "price": 2500},
        {"name": "라볶이", "price": 5500},
        {"name": "튀김 모둠", "price": 3500},
    ]
