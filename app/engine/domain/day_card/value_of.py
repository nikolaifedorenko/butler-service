"""value_of(day, st) — значение Табеля (3.3, единственное нормативное место):
`<код>` без часов; `<код> <часы>` с часами — ровно один пробел, дробь через запятую,
≤ 2 знаков, без хвостовых нулей (RUL-TIMESHEET-VALUE)."""
from __future__ import annotations

from ..settings.types import Settings
from ..types.entities import Day
from .fmt_hours import fmt_hours
from .policy_of import policy_of


def value_of(day: Day, st: Settings) -> str:
    if not policy_of(day, st).carries_hours:
        return day.code
    return f"{day.code} {fmt_hours(day.plan_minutes)}"
