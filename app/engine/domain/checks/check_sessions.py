"""INV-INTERVAL-WITHIN-DAY и INV-GRID для расчётных интервалов (10.1: после стадии 4)."""
from __future__ import annotations

import datetime as dt
from typing import Mapping, Sequence

from ..codes_registry.invariant_codes import INV_GRID, INV_INTERVAL_WITHIN_DAY
from ..types.entities import Interval
from ._fail import fail


def _check_one(iv: Interval, step: int) -> None:
    if not (0 <= iv.start_minute <= iv.end_minute <= 1440):
        fail(INV_INTERVAL_WITHIN_DAY, {"day": iv.day, "start": iv.start_minute, "end": iv.end_minute})
    if iv.start_minute % step or iv.end_minute % step:
        fail(INV_GRID, {"day": iv.day, "start": iv.start_minute, "end": iv.end_minute})


def check_sessions(intervals: Mapping[dt.date, Sequence[Interval]], step: int) -> None:
    for day, items in intervals.items():
        for iv in items:
            _check_one(iv, step)
        if sum(i.length for i in items) > 1440:
            fail(INV_INTERVAL_WITHIN_DAY, {"day": day, "fact": sum(i.length for i in items)})
