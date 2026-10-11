"""Локальная полночь дня в tz настроек (4.4). Локальные сутки — всегда 1440 минут;
DST игнорируется (4.5, решение владельца R24)."""
from __future__ import annotations

import datetime as dt

from ..settings.types import Settings


def local_midnight(day: dt.date, tz) -> dt.datetime:
    return dt.datetime.combine(day, dt.time(0), tz)


def next_midnight(day: dt.date, tz) -> dt.datetime:
    return local_midnight(day + dt.timedelta(days=1), tz)


def midnight_of_settings(day: dt.date, st: Settings) -> dt.datetime:
    return local_midnight(day, st.tz)
