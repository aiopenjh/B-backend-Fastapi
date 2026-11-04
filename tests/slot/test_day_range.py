# [담당3-영민] DayRange 도메인 테스트
from datetime import date, datetime, timedelta

from slot.domain.day_range import SEOUL, seoul_day_range, seoul_now


def test_seoul_day_range_is_half_open_24h():
    start, end = seoul_day_range(date(2026, 11, 5))
    assert start == datetime(2026, 11, 5, 0, 0, tzinfo=SEOUL)    # ▶ 그날 00:00+09:00
    assert end == datetime(2026, 11, 6, 0, 0, tzinfo=SEOUL)      # ▶ 다음 날 00:00+09:00 (포함 안 함)
    assert end - start == timedelta(days=1)


def test_seoul_offset_is_plus_nine():
    assert seoul_now().utcoffset() == timedelta(hours=9)         # ▶ common/schemas.py 의 SEOUL 과 같은 오프셋 — 둘이 어긋나면 responded_at 과 starts_at 의 +09:00 이 달라진다