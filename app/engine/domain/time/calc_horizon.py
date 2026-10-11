"""calc_horizon(period, now_calc, st) — горизонт H = min(now_calc, полночь дня после
period.end) (4.4, RUL-HORIZON). Для флагов вызывается с исходным now → H_raw."""
from __future__ import annotations

import datetime as dt

from ..settings.types import Settings
from ..types.entities import Period
from .local_midnight import next_midnight


def calc_horizon(period: Period, now_calc: dt.datetime, st: Settings) -> dt.datetime:
    return min(now_calc, next_midnight(period.end, st.tz))
