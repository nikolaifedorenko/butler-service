"""late_flag — LATE (6.6): для каждого ожидаемого подинтервала S:
now ≥ S.start + лимит ∧ ¬present_at(S.start) ∧ (actual_at = None ∨ actual_at > S.start + лимит).
actual_at — по исходным интервалам; None — след «ожидался — не пришёл» (v7/R21),
живёт до конца дня и остаётся в снимке закрытого периода (RUL-LATE-NONE-PERSISTS)."""
from __future__ import annotations

import datetime as dt
from typing import Sequence

from ..codes_registry.flag_codes import LATE
from ..schedule.shift_segments import Segment
from ..settings.types import Settings
from ..types.entities import RawInterval
from ..types.results import Flag
from ._actual import first_start_in
from .present_at import present_at


def _flag(sub: Segment, intervals: Sequence[RawInterval], now: dt.datetime,
          st: Settings) -> Flag | None:
    limit = dt.timedelta(minutes=st.late_limit_minutes)
    if now < sub[0] + limit or present_at(intervals, sub[0]):
        return None
    actual = first_start_in(sub, intervals)
    if actual is not None and actual <= sub[0] + limit:
        return None
    day = sub[0].astimezone(st.tz).date()
    return Flag(day, LATE, {"expected_at": sub[0], "actual_at": actual})


def late_flag(subintervals: Sequence[Segment], intervals: Sequence[RawInterval],
              now: dt.datetime, st: Settings) -> tuple[Flag, ...]:
    flags = (_flag(s, intervals, now, st) for s in subintervals)
    return tuple(f for f in flags if f is not None)
