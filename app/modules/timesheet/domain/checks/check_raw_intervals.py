"""INV-INTERVAL-WITHIN-DAY для RawInterval (10.1: в evaluate_flags после
raw_presence_intervals). INV-GRID на исходные интервалы не распространяется —
они хранят секунды (4.5)."""
from __future__ import annotations

import datetime as dt
from typing import Mapping, Sequence

from ..codes_registry.invariant_codes import INV_INTERVAL_WITHIN_DAY
from ..settings.types import Settings
from ..time.local_midnight import local_midnight, next_midnight
from ..types.entities import RawInterval
from ._fail import fail


def check_raw_intervals(intervals: Mapping[dt.date, Sequence[RawInterval]], st: Settings) -> None:
    for day, items in intervals.items():
        lo, hi = local_midnight(day, st.tz), next_midnight(day, st.tz)
        for iv in items:
            if not (lo <= iv.start_utc < iv.end_utc <= hi):
                fail(INV_INTERVAL_WITHIN_DAY,
                     {"day": day, "start": iv.start_utc.isoformat(), "end": iv.end_utc.isoformat()})
