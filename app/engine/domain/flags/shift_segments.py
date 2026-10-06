import datetime as dt
from typing import Sequence

from ..time.day_of_moment import day_of_moment
from ..time.local_minute import local_minute
from ..types.entities import KIND_IN, KIND_OUT, Interval, Shift


def _split(shift: Shift, tz: str) -> list[Interval]:
    first = day_of_moment(shift.start_utc, KIND_IN, tz)
    last = day_of_moment(shift.end_utc, KIND_OUT, tz)
    days = [first + dt.timedelta(days=i) for i in range((last - first).days + 1)]
    return [Interval(d, max(0, local_minute(shift.start_utc, d, tz)),
                     min(1440, local_minute(shift.end_utc, d, tz))) for d in days]


def shift_segments(shifts: Sequence[Shift], tz: str) -> tuple[Interval, ...]:
    """Р31: смена через полночь → календарные отрезки (И16)."""
    return tuple(s for sh in shifts for s in _split(sh, tz) if s.end_minute > s.start_minute)
