import datetime as dt

from ..time.local_minute import local_minute


def end_minute_of_day(day: dt.date, today: dt.date, now_moment: dt.datetime, tz: str) -> int:
    """1440 для прошедшего дня, min(now, 24:00) для сегодня, 0 для будущего (Р29)."""
    if day != today:
        return 1440 if day < today else 0
    return min(1440, local_minute(now_moment, day, tz))
