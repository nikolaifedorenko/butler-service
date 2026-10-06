from typing import Sequence

from ..settings.types import Window
from ..types.entities import Interval
from .overlap import overlap


def cut_working_time(intervals: Sequence[Interval], window: Window | None) -> int:
    """Рабочее время = полный факт ∩ окно (Р8)."""
    segments = window.segments if window else ()
    return sum(overlap((i.start_minute, i.end_minute), s) for i in intervals for s in segments)
