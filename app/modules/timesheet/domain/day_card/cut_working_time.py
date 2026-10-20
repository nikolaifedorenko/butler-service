"""cut_working_time(intervals, window) — рабочее время: полный факт ∩ окно
(RUL-WORK-AND-OVERTIME); window = None → 0."""
from __future__ import annotations

from typing import Sequence

from ..settings.types import Window
from ..types.entities import Interval, Minutes
from ._overlap import overlap_minutes


def cut_working_time(intervals: Sequence[Interval], window: Window | None) -> Minutes:
    if window is None:
        return 0
    return sum(overlap_minutes(iv, window.start_minute, window.end_minute) for iv in intervals)
