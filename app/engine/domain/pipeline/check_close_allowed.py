import datetime as dt

from ..time.local_midnight import local_midnight
from ..types.entities import Period
from ..types.errors import IncompletePeriodError


def check_close_allowed(period: Period, now: dt.datetime, mode: str, tz: str) -> None:
    """Стадия 1: close — только если исходный now ≥ 00:00 дня после period.end."""
    if mode == "close" and now < local_midnight(period.end + dt.timedelta(days=1), tz):
        raise IncompletePeriodError(period.end, now)
