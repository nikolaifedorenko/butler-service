"""overtime_parts(intervals, window) — части полного факта вне окна (переработка);
план не участвует — «сверхплановых» минут в модели нет (4.2, v7). window = None →
весь факт — переработка."""
from __future__ import annotations

from typing import Sequence

from ..settings.types import Window
from ..types.entities import Interval


def _outside(iv: Interval, window: Window | None) -> tuple[Interval, ...]:
    if window is None:
        return (iv,)
    before = Interval(iv.day, iv.start_minute, min(iv.end_minute, window.start_minute))
    after = Interval(iv.day, max(iv.start_minute, window.end_minute), iv.end_minute)
    return tuple(p for p in (before, after) if p.length > 0)


def overtime_parts(intervals: Sequence[Interval], window: Window | None) -> tuple[Interval, ...]:
    return tuple(part for iv in intervals for part in _outside(iv, window))
