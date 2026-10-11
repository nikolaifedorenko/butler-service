"""early_flag — EARLY_DEPARTURE (6.6): now ≥ S.end ∧ в S есть исходное присутствие ∧
last_end(S) < S.end − лимит. При отсутствии присутствия в S флаг не ставится (случай
покрывает LATE с actual_at = None); уход ровно в S.end — флаг не ставится."""
from __future__ import annotations

import datetime as dt
from typing import Sequence

from ..codes_registry.flag_codes import EARLY_DEPARTURE
from ..schedule.shift_segments import Segment
from ..settings.types import Settings
from ..types.entities import RawInterval
from ..types.results import Flag
from ._actual import last_end_in


def _flag(sub: Segment, intervals: Sequence[RawInterval], now: dt.datetime,
          st: Settings) -> Flag | None:
    limit = dt.timedelta(minutes=st.late_limit_minutes)
    if now < sub[1]:
        return None
    last_end = last_end_in(sub, intervals)
    if last_end is None or last_end >= sub[1] - limit:
        return None
    day = sub[0].astimezone(st.tz).date()
    return Flag(day, EARLY_DEPARTURE, {"expected_at": sub[1], "actual_at": last_end})


def early_flag(subintervals: Sequence[Segment], intervals: Sequence[RawInterval],
               now: dt.datetime, st: Settings) -> tuple[Flag, ...]:
    flags = (_flag(s, intervals, now, st) for s in subintervals)
    return tuple(f for f in flags if f is not None)
