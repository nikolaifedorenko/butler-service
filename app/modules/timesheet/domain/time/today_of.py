"""today_of(now, st) — локальная дата исходного now (4.4: «сегодня» — по исходному now)."""
from __future__ import annotations

import datetime as dt

from ..settings.types import Settings


def today_of(now: dt.datetime, st: Settings) -> dt.date:
    return now.astimezone(st.tz).date()
