import datetime as dt
from typing import Sequence

from ..time.local_minute import local_minute
from ..types.entities import CLOSED, KIND_IN, OPEN, CalcMark, Interval


def day_intervals(day_marks: Sequence[CalcMark], state: str, day: dt.date, end_minute: int,
                  tz: str) -> tuple[tuple[Interval, ...], str]:
    """Интервалы дня по правилу 4.3; возвращает интервалы и состояние на конец дня."""
    start = 0 if state == OPEN else None
    spans = []
    for m in day_marks:
        minute = local_minute(m.at_calc, day, tz)
        if m.source.kind == KIND_IN:
            start = minute
        elif start is not None:
            spans.append((start, minute))
            start = None
    if start is not None:
        spans.append((start, end_minute))
    out = tuple(Interval(day, a, b) for a, b in spans if b > a)
    return out, (OPEN if start is not None else CLOSED)
