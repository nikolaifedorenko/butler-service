import datetime as dt
from dataclasses import dataclass
from typing import Mapping, Sequence

from ..types.entities import OPEN, CalcMark, Interval
from .day_intervals import day_intervals
from .end_minute_of_day import end_minute_of_day
from .marks_of_day import marks_of_day
from .state_before import state_before


@dataclass(frozen=True)
class Presence:
    intervals: Mapping[dt.date, tuple[Interval, ...]]
    open_at_start: Mapping[dt.date, bool]
    open_at_end: Mapping[dt.date, bool]


def presence_intervals(days: Sequence[dt.date], marks: Sequence[CalcMark], now_moment: dt.datetime,
                       today: dt.date, tz: str) -> Presence:
    """Композиция 4.3 по всем дням периода с переносом состояния через полночь."""
    state = state_before(marks, days[0]) if days else "closed"
    intervals, starts, ends = {}, {}, {}
    for day in days:
        starts[day] = state == OPEN
        end = end_minute_of_day(day, today, now_moment, tz)
        intervals[day], state = day_intervals(marks_of_day(marks, day), state, day, end, tz)
        ends[day] = state == OPEN
    return Presence(intervals, starts, ends)
