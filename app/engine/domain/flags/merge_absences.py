import datetime as dt
from typing import Sequence

from ..types.entities import Absence
from .merge_spans import merge_spans


def merge_absences(absences: Sequence[Absence]) -> dict[dt.date, tuple[tuple[int, int], ...]]:
    """Канонический список согласованных отсутствий по дням (5.1)."""
    days = sorted({a.day for a in absences})
    return {d: merge_spans((a.start_minute, a.end_minute) for a in absences if a.day == d) for d in days}
