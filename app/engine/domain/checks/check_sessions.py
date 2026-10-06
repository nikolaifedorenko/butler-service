import datetime as dt
from typing import Mapping

from ..codes_registry.invariant_codes import I12, I18
from ..types.entities import Interval
from ._fail import fail_if


def check_sessions(intervals: Mapping[dt.date, tuple[Interval, ...]], step: int) -> None:
    """И12: интервал внутри дня, факт дня ≤ 24 ч; И18: границы кратны шагу."""
    for day, items in intervals.items():
        fail_if(sum(i.length for i in items) > 1440, I12, day=day)
        for i in items:
            fail_if(not (i.day == day and 0 <= i.start_minute < i.end_minute <= 1440), I12, day=day)
            fail_if(i.start_minute % step or i.end_minute % step, I18, day=day, interval=i)
