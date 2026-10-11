"""CHK-NOW-IN-PERIOD (5.3, 4.4): исходный now ≥ 00:00 period.start в st.tz — иначе
горизонт H оказался бы левее периода и все дни молча получили бы недостачу = окно."""
from __future__ import annotations

import datetime as dt

from ..settings.types import Settings
from ..time.local_midnight import local_midnight
from ..types.entities import Period
from ..types.errors import InvalidInputDataError


def check_now_in_period(period: Period, now: dt.datetime, st: Settings) -> None:
    if now < local_midnight(period.start, st.tz):
        raise InvalidInputDataError("CHK-NOW-IN-PERIOD", {"now": now, "period_start": period.start})
