"""presence_board(now) — вкладка «Отметки» (16.2): ≤ 5 батч-запросов, популяция —
трудоустроенные на «сегодня» (v7.1/R38, фильтрация здесь — домен о трудоустройстве
не знает); тяжёлый конвейер не вызывается (16.1 п.2)."""
from __future__ import annotations

import datetime as dt

from ..domain.board.assemble_board import assemble_board
from ..domain.types.results import PresenceBoard
from .context import EnginePorts
from .months import settings_for_now


def presence_board(now: dt.datetime, ports: EnginePorts) -> PresenceBoard:
    # Settings — для месяца, содержащего ЛОКАЛЬНОЕ «сегодня» (16.2; P1-ts-4:
    # прежняя загрузка по UTC-дню на границе месяцев брала справочники прошлого
    # месяца). В обычном случае один load; на границе — второй, для нового месяца.
    st, today = settings_for_now(now, ports)                          # разрешение Settings
    active = set(ports.employment.active_employees(today))                 # запрос 1
    last_marks = [m for m in ports.punch.last_marks(now)                   # запрос 2
                  if m.employee_id in active]
    shifts = [s for s in ports.shift.shifts_on_day(today)                  # запрос 3
              if s.employee_id in active]
    absences = [a for a in ports.absence.absences_on_day(today)            # запрос 4
                if a.employee_id in active]
    return assemble_board(last_marks, shifts, absences, now, st)
