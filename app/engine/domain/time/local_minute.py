import datetime as dt

from .local_midnight import local_midnight


def local_minute(t: dt.datetime, day: dt.date, tz: str) -> int:
    """Минута момента внутри дня day (0..1440); 1440 — его 24:00."""
    return int((t - local_midnight(day, tz)) // dt.timedelta(minutes=1))
