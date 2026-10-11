"""expected_now(shifts, absences, now, st) — (b) сколько должно быть по Графику прямо
сейчас: now внутри ожидаемого подинтервала в смысле [start, end) — в момент S.start
сотрудник уже ожидается (16.2, v7)."""
from __future__ import annotations

import datetime as dt
from typing import Sequence

from ..settings.types import Settings
from ..types.entities import Absence, Shift
from ._today import day_context, group_by_employee


def _expected(shifts: Sequence[Shift], absences: Sequence[Absence], now: dt.datetime,
              st: Settings) -> bool:
    _, _, subs = day_context(shifts, absences, now, st)
    return any(start <= now < end for start, end in subs)


def expected_now(shifts: Sequence[Shift], absences: Sequence[Absence], now: dt.datetime,
                 st: Settings) -> int:
    by_emp_shifts = group_by_employee(shifts)
    by_emp_absences = group_by_employee(absences)
    employees = set(by_emp_shifts) | set(by_emp_absences)
    return sum(1 for emp in employees
               if _expected(by_emp_shifts.get(emp, ()), by_emp_absences.get(emp, ()), now, st))
