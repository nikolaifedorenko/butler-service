from typing import Sequence

from ..settings.types import Window
from ..types.entities import Interval
from .subtract_segments import subtract_segments


def overtime_parts(intervals: Sequence[Interval], window: Window | None) -> tuple[Interval, ...]:
    """Части интервалов вне окна; без окна — все интервалы целиком."""
    segments = window.segments if window else ()
    return tuple(p for i in intervals for p in subtract_segments(i, segments))
