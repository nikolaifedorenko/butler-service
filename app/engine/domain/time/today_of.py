import datetime as dt

from ._tz import zone


def today_of(now: dt.datetime, tz: str) -> dt.date:
    """«Сегодня» — локальная дата исходного now."""
    return now.astimezone(zone(tz)).date()
