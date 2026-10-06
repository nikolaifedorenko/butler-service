from typing import Sequence

from ..types.entities import Interval


def fact_of_day(intervals: Sequence[Interval]) -> int:
    """Полный факт — сумма длин интервалов."""
    return sum(i.length for i in intervals)
