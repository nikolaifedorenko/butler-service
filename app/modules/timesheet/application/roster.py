"""Публичный запрос «смены и отсутствия сотрудников на даты» (для модуля «Шахматка»,
спецификация 2026-10-23, §5): три пакетных запроса на любой диапазон — смены Графика,
согласованные отсутствия и коды дней Табеля. Смена относится к дню своего начала."""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Sequence

from app.core.time import TZ

from ..domain.types.entities import Period
from .context import EnginePorts


@dataclass(frozen=True)
class RosterDay:
    on_shift: bool
    tabel_code: str | None
    absence_minutes: int          # согласованные отсутствия внутри смен дня


def _overlap(a0: dt.datetime, a1: dt.datetime, b0: dt.datetime, b1: dt.datetime) -> int:
    return max(0, int((min(a1, b1) - max(a0, b0)).total_seconds() // 60))


def roster(employee_ids: Sequence[int], first: dt.date, last: dt.date,
           ports: EnginePorts) -> dict[tuple[int, dt.date], RosterDay]:
    """Ключ — (сотрудник, день); дня нет в ответе — ни смены, ни кода Табеля."""
    if not employee_ids:
        return {}
    ids = [str(e) for e in employee_ids]
    period = Period(first, last)
    shifts: dict[tuple[int, dt.date], list] = {}
    for s in ports.shift.shifts_for(ids, period):
        day = s.start_utc.astimezone(TZ).date()
        if first <= day <= last:
            shifts.setdefault((int(s.employee_id), day), []).append(s)
    absences: dict[int, list] = {}
    for a in ports.absence.absences_for(ids, period):
        absences.setdefault(int(a.employee_id), []).append(a)
    codes = ports.timesheet.codes_for(ids, period)
    out: dict[tuple[int, dt.date], RosterDay] = {}
    for key in set(shifts) | {(int(e), d) for e, d in codes}:
        day_shifts = shifts.get(key, [])
        minutes = sum(_overlap(s.start_utc, s.end_utc, a.start_utc, a.end_utc)
                      for s in day_shifts for a in absences.get(key[0], []))
        out[key] = RosterDay(bool(day_shifts), codes.get((str(key[0]), key[1])), minutes)
    return out
