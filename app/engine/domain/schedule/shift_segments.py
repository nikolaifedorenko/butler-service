"""shift_segments(shifts, st) — разложить смены на дневные отрезки (4.7): смена через
полночь даёт отрезки каждому дню (INV-SEGMENT-WITHIN-DAY); смежные и пересекающиеся
отрезки в пределах дня сливаются (v7/R17)."""
from __future__ import annotations

import datetime as dt
from typing import Mapping, Sequence

from ..settings.types import Settings
from ..time.local_midnight import local_midnight, next_midnight
from ..types.entities import Shift

Segment = tuple[dt.datetime, dt.datetime]


def _pieces(shift: Shift, st: Settings) -> list[tuple[dt.date, Segment]]:
    first = shift.start_utc.astimezone(st.tz).date()
    last = (shift.end_utc - dt.timedelta(microseconds=1)).astimezone(st.tz).date()
    out = []
    day = first
    while day <= last:
        piece = (max(shift.start_utc, local_midnight(day, st.tz)),
                 min(shift.end_utc, next_midnight(day, st.tz)))
        if piece[0] < piece[1]:
            out.append((day, piece))
        day += dt.timedelta(days=1)
    return out


def merge_spans(spans: Sequence[Segment]) -> tuple[Segment, ...]:
    """Слияние пересекающихся и примыкающих отрезков на одной оси (v7/R17)."""
    out: list[Segment] = []
    for start, end in sorted(spans):
        if out and start <= out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][1], end))
        else:
            out.append((start, end))
    return tuple(out)


def shift_segments(shifts: Sequence[Shift],
                   st: Settings) -> Mapping[dt.date, tuple[Segment, ...]]:
    per_day: dict[dt.date, list[Segment]] = {}
    for shift in shifts:
        for day, piece in _pieces(shift, st):
            per_day.setdefault(day, []).append(piece)
    return {day: merge_spans(spans) for day, spans in per_day.items()}
