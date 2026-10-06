import datetime as dt
from typing import Mapping, Sequence

from ..day_card.subtract_segments import subtract_segments
from ..types.entities import Interval
from .merge_spans import merge_spans


def expected_subintervals(segments: Sequence[Interval], absences: Mapping[dt.date, tuple],
                          day: dt.date) -> tuple[Interval, ...]:
    """Отрезки смен дня минус согласованные отсутствия → ожидаемые подинтервалы."""
    spans = merge_spans((s.start_minute, s.end_minute) for s in segments if s.day == day)
    holes = absences.get(day, ())
    return tuple(p for a, b in spans for p in subtract_segments(Interval(day, a, b), holes))
