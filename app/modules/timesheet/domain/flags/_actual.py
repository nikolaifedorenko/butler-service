"""Фактические моменты по исходным интервалам дня (6.6, формулы условий флагов)."""
from __future__ import annotations

import datetime as dt
from typing import Sequence

from ..schedule.shift_segments import Segment
from ..types.entities import RawInterval


def first_start_in(sub: Segment, intervals: Sequence[RawInterval]) -> dt.datetime | None:
    """actual_at у LATE: min{s.start} по интервалам с S.start ≤ s.start < S.end."""
    starts = [iv.start_utc for iv in intervals if sub[0] <= iv.start_utc < sub[1]]
    return min(starts) if starts else None


def last_end_in(sub: Segment, intervals: Sequence[RawInterval]) -> dt.datetime | None:
    """last_end(S) у EARLY_DEPARTURE: max{min(s.end, S.end)} по интервалам, пересекающим S."""
    ends = [min(iv.end_utc, sub[1]) for iv in intervals if iv.start_utc < sub[1] and iv.end_utc > sub[0]]
    return max(ends) if ends else None
