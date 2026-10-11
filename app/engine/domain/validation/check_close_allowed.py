"""CHK-CLOSE-ALLOWED (5.3, 4.4): для close исходный now ≥ 00:00 дня после period.end
в st.tz → IncompletePeriodError. Округление 23:40 до 00:00 права на закрытие не даёт."""
from __future__ import annotations

import datetime as dt

from ..settings.types import Settings
from ..time.local_midnight import next_midnight
from ..types.entities import Period
from ..types.errors import IncompletePeriodError


def check_close_allowed(period: Period, now: dt.datetime, mode: str, st: Settings) -> None:
    if mode == "close" and now < next_midnight(period.end, st.tz):
        raise IncompletePeriodError(period.end, now)
