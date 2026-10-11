"""presence_board(now) — вкладка «Отметки» (16.2): ≤ 5 батч-запросов, популяция —
трудоустроенные на «сегодня» (v7.1/R38, фильтрация здесь — домен о трудоустройстве
не знает); тяжёлый конвейер не вызывается (16.1 п.2)."""
from __future__ import annotations

import datetime as dt

from ..domain.board.assemble_board import assemble_board
from ..domain.time.today_of import today_of
from ..domain.types.results import PresenceBoard
from .context import EnginePorts
from .months import month_period


def presence_board(now: dt.datetime, ports: EnginePorts) -> PresenceBoard:
    utc_day = now.astimezone(dt.timezone.utc).date()
    st = ports.settings.load(month_period(utc_day.year, utc_day.month))   # запрос 1 (16.2:
    today = today_of(now, st)                       # Settings грузятся для месяца «сегодня»)
    active = set(ports.employment.active_employees(today))                 # запрос 2
    last_marks = [m for m in ports.punch.last_marks(now)                   # запрос 3
                  if m.employee_id in active]
    shifts = [s for s in ports.shift.shifts_on_day(today)                  # запрос 4
              if s.employee_id in active]
    absences = [a for a in ports.absence.absences_on_day(today)            # запрос 5
                if a.employee_id in active]
    return assemble_board(last_marks, shifts, absences, now, st)
