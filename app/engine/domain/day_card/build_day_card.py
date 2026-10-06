from typing import Sequence

from ..settings.types import Settings
from ..types.entities import CalcMark, Day, Interval
from ..types.results import DayCard
from .apply_plan_equals_fact import apply_plan_equals_fact
from .codes_of_day import codes_of_day
from .cut_working_time import cut_working_time
from .debt_of_day import debt_of_day
from .fact_of_day import fact_of_day
from .has_presence import has_presence
from .overtime_parts import overtime_parts
from .pays_overtime import pays_overtime
from .plan_of_day import plan_of_day
from .value_of import value_of
from .window_of_day import window_of_day


def build_day_card(day: Day, intervals: Sequence[Interval], day_marks: Sequence[CalcMark],
                   open_at_start: bool, open_at_end: bool, st: Settings) -> DayCard:
    """Композиция стадии 5."""
    window = window_of_day(day, st)
    plan0 = plan_of_day(day, st)
    plan = apply_plan_equals_fact(day, plan0, has_presence(day_marks, open_at_start), st)
    work = cut_working_time(intervals, window)
    parts = overtime_parts(intervals, window)
    return DayCard(day=day.day, timesheet_value=value_of(day, st), plan_minutes=plan,
                   full_fact_minutes=fact_of_day(intervals), work_minutes=work,
                   overtime_minutes=sum(p.length for p in parts), debt_minutes=debt_of_day(plan, work),
                   codes=codes_of_day(day, parts, st), pays_overtime=pays_overtime(day, st),
                   open_at_start=open_at_start, open_at_end=open_at_end,
                   plan_equals_fact_applied=plan != plan0)
