"""assemble_board(last_marks, shifts, absences, now, st) — композиция доски (16.2;
сигнатура зафиксирована в v7.1). Популяцию (только трудоустроенные сегодня — v7.1/R38)
фильтрует use case presence_board до вызова: домен о трудоустройстве не знает."""
from __future__ import annotations

import datetime as dt
from typing import Sequence

from ..settings.types import Settings
from ..types.entities import Absence, Mark, Shift
from ..types.results import EmployeeCard, PresenceBoard
from ._today import day_context, group_by_employee
from .expected_arrivals import expected_arrivals
from .expected_now import expected_now
from .open_sessions import open_sessions


def _minutes_open(now: dt.datetime, open_since: dt.datetime) -> int:
    return int((now - open_since).total_seconds() // 60)


def _card(emp: str, open_since: dt.datetime, shifts: Sequence[Shift],
          absences: Sequence[Absence], now: dt.datetime, st: Settings) -> EmployeeCard:
    segments, _, subs = day_context(shifts, absences, now, st)
    return EmployeeCard(emp, open_since, _minutes_open(now, open_since),
                        bool(subs), tuple(segments))


def assemble_board(last_marks: Sequence[Mark], shifts: Sequence[Shift],
                   absences: Sequence[Absence], now: dt.datetime,
                   st: Settings) -> PresenceBoard:
    opened = open_sessions(last_marks, now)
    by_emp_shifts = group_by_employee(shifts)
    by_emp_absences = group_by_employee(absences)
    cards = tuple(_card(emp, since, by_emp_shifts.get(emp, ()), by_emp_absences.get(emp, ()),
                        now, st) for emp, since in opened)
    present_ids = {emp for emp, _ in opened}
    return PresenceBoard(len(opened), expected_now(shifts, absences, now, st), cards,
                         expected_arrivals(shifts, absences, present_ids, now, st))
