"""expected_arrivals(shifts, absences, present_ids, now, st) — (d) «кто ещё должен
прийти» (16.2): ожидаемые подинтервалы сегодня, где сотрудника нет сейчас; завершившиеся
(S.end ≤ now) не входят (v7/R20 — непроход фиксирует LATE(None) во флагах); не более
одной записи на сотрудника — ближайший незавершённый подинтервал (v7.1/R40)."""
from __future__ import annotations

import datetime as dt
from typing import AbstractSet, Sequence

from ..settings.types import Settings
from ..types.entities import Absence, Shift
from ..types.results import ExpectedArrival
from ._today import day_context, group_by_employee


def _arrival(emp: str, shifts: Sequence[Shift], absences: Sequence[Absence],
             now: dt.datetime, st: Settings) -> ExpectedArrival | None:
    _, _, subs = day_context(shifts, absences, now, st)
    upcoming = [s for s in subs if s[1] > now]
    if not upcoming:
        return None
    start = min(upcoming)[0]
    return ExpectedArrival(emp, start, already_started=start <= now)


def expected_arrivals(shifts: Sequence[Shift], absences: Sequence[Absence],
                      present_ids: AbstractSet[str], now: dt.datetime,
                      st: Settings) -> tuple[ExpectedArrival, ...]:
    by_emp_shifts = group_by_employee(shifts)
    by_emp_absences = group_by_employee(absences)
    employees = (set(by_emp_shifts) | set(by_emp_absences)) - set(present_ids)
    arrivals = [a for a in (_arrival(e, by_emp_shifts.get(e, ()), by_emp_absences.get(e, ()),
                                     now, st) for e in employees) if a is not None]
    return tuple(sorted(arrivals, key=lambda a: (a.expected_at_utc, a.employee_id)))
