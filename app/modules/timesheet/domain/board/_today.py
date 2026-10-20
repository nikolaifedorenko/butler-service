"""Общий контекст сегодняшнего дня для доски: отрезки смен, слитые отсутствия,
ожидаемые подинтервалы (16.2)."""
from __future__ import annotations

import datetime as dt
from typing import Mapping, Sequence

from ..schedule.expected_subintervals import expected_subintervals
from ..schedule.merge_absences import merge_absences
from ..schedule.shift_segments import Segment, shift_segments
from ..settings.types import Settings
from ..time.today_of import today_of
from ..types.entities import Absence, Shift


def group_by_employee(items) -> Mapping[str, list]:
    out: dict[str, list] = {}
    for item in items:
        out.setdefault(item.employee_id, []).append(item)
    return out


def day_context(shifts: Sequence[Shift], absences: Sequence[Absence], now: dt.datetime,
                st: Settings) -> tuple[tuple[Segment, ...], tuple[Segment, ...], tuple[Segment, ...]]:
    """(отрезки смены сегодня без вычета отсутствий, слитые отсутствия, ожидаемые подинтервалы)."""
    today = today_of(now, st)
    segments = shift_segments(shifts, st).get(today, ())
    merged = merge_absences(absences)
    return segments, merged, expected_subintervals(segments, merged, today)
