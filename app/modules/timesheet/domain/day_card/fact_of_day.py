"""fact_of_day(intervals) — полный факт дня: сумма длин расчётных интервалов (4.2)."""
from __future__ import annotations

from typing import Sequence

from ..types.entities import Interval, Minutes


def fact_of_day(intervals: Sequence[Interval]) -> Minutes:
    return sum(iv.length for iv in intervals)
