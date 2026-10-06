import datetime as dt
from typing import Mapping, Sequence

from ..settings.types import Settings
from ..types.entities import CalcMark, Day, Interval
from ..types.results import DayCard, Flag
from .activity_review import activity_review_flags
from .early import early_flag
from .expected_subintervals import expected_subintervals
from .gap import gap_flags
from .late import late_flag
from .missed import missed_flag
from .off_shift import off_shift_flag


def day_flags(day: Day, card: DayCard | None, intervals: Sequence[Interval], segments: Sequence[Interval],
              absences: Mapping[dt.date, tuple], calc_marks: Sequence[CalcMark], now_minute: int,
              st: Settings) -> tuple[Flag, ...]:
    """Флаги одного дня — каждая проверка отдельной функцией."""
    subs = expected_subintervals(segments, absences, day.day)
    own = [s for s in segments if s.day == day.day]
    per_sub = [f(s, intervals, now_minute, st) for s in subs for f in (late_flag, early_flag)]
    single = [missed_flag(subs, intervals, card, now_minute),
              off_shift_flag(subs, intervals, own, absences.get(day.day, ()), st)]
    found = [*gap_flags(subs), *per_sub, *single, *activity_review_flags(day, calc_marks, st)]
    return tuple(f for f in found if f is not None)
