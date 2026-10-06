import datetime as dt

from ._tz import zone


def local_midnight(day: dt.date, tz: str) -> dt.datetime:
    """Момент UTC локальной полуночи дня."""
    return dt.datetime(day.year, day.month, day.day, tzinfo=zone(tz)).astimezone(dt.timezone.utc)
