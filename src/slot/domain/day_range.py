# [담당3-영민] DayRange 도메인 구현
from datetime import date, datetime, time, timedelta, timezone

SEOUL = timezone(timedelta(hours=9), "Asia/Seoul")

def seoul_day_range(day: date) -> tuple[datetime, datetime]:
    """ 서울 기준 하루 시작과 끝의 날짜를 반환 """
    start = datetime.combine(day, time.min, tzinfo=SEOUL)
    return start, start + timedelta(days=1)

def seoul_now() -> datetime:
    return datetime.now(SEOUL)