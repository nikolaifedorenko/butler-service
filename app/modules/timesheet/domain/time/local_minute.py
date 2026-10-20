"""local_minute(t, day, st) — минута внутри локального дня 0..1440 (3.1)."""
from __future__ import annotations

import datetime as dt

from ..settings.types import Settings
from .local_midnight import local_midnight


def local_minute(t: dt.datetime, day: dt.date, st: Settings) -> int:
    return int((t.astimezone(st.tz) - local_midnight(day, st.tz)).total_seconds() // 60)
