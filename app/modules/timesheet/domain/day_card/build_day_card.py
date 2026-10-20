"""build_day_card — композиция карточки дня (2.2, 6.3 стадия 5):
window → fact → has_event → plan/applied → work → parts → debt → codes → DayCard.
timesheet_value — по информационному плану строки (ключ CFG-WINDOWS); план карточки —
от окна (v7.1/R34)."""
from __future__ import annotations

from typing import Sequence

from ..settings.types import Settings
from ..types.entities import Day, Interval, Mark
from ..types.results import DayCard
from .apply_plan_equals_fact import apply_plan_equals_fact
from .codes_of_day import codes_of_day
from .cut_working_time import cut_working_time
from .debt_of_day import debt_of_day
from .fact_of_day import fact_of_day
from .has_presence_event import has_presence_event
from .overtime_parts import overtime_parts
from .pays_overtime import pays_overtime
from .plan_of_day import plan_of_day
from .value_of import value_of
from .window_of_day import window_of_day


def build_day_card(day: Day, intervals: Sequence[Interval], day_raw_marks: Sequence[Mark],
                   st: Settings) -> DayCard:
    window = window_of_day(day, st)
    fact = fact_of_day(intervals)
    has_event = has_presence_event(day, day_raw_marks, st)
    plan, applied = apply_plan_equals_fact(day, fact, plan_of_day(day, st), has_event, st)
    work = cut_working_time(intervals, window)
    parts = overtime_parts(intervals, window)
    debt = debt_of_day(day, work, applied, st)
    return DayCard(day=day.day, timesheet_value=value_of(day, st), plan_minutes=plan,
                   full_fact_minutes=fact, work_minutes=work, overtime_minutes=fact - work,
                   debt_minutes=debt, codes=codes_of_day(day, parts, st),
                   pays_overtime=pays_overtime(day, st), plan_equals_fact_applied=applied)
