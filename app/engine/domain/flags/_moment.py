import datetime as dt

from ..time.local_midnight import local_midnight


def moment_of(day: dt.date, minute: int, tz: str) -> dt.datetime:
    """UTC-момент минуты локального дня."""
    return local_midnight(day, tz) + dt.timedelta(minutes=minute)
