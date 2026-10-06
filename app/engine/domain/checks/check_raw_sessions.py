import datetime as dt
from typing import Mapping

from ..codes_registry.invariant_codes import I12
from ..types.entities import Interval
from ._fail import fail_if


def check_raw_sessions(intervals: Mapping[dt.date, tuple[Interval, ...]]) -> None:
    """И12 для исходных интервалов флагов (И18 к ним не применяется — они не округляются)."""
    for day, items in intervals.items():
        for i in items:
            fail_if(not (i.day == day and 0 <= i.start_minute < i.end_minute <= 1440), I12, day=day)
