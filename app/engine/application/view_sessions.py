"""view_sessions — вкладка «Факт» (16.4): история сессий на общем ядре pair_marks
(без горизонта, исходные моменты, без округления и нарезки); три индексных запроса;
вкладочные признаки диапазона — SessionView.started_before_range / closed_after_range."""
from __future__ import annotations

import datetime as dt

from ..domain.sessions.pair_marks import pair_marks
from ..domain.types.entities import KIND_IN, KIND_OUT
from ..domain.types.results import SessionView
from .context import EnginePorts


def _views(employee_id: str, sessions, opening, closing) -> tuple[SessionView, ...]:
    started_before = opening is not None and opening.kind == KIND_IN
    tail_closed_after = (closing is not None and closing.kind == KIND_OUT and sessions
                         and sessions[-1].end == closing.at_utc)
    out = []
    for index, session in enumerate(sessions):
        out.append(SessionView(employee_id, session,
                               started_before_range=started_before and index == 0,
                               closed_after_range=tail_closed_after and index == len(sessions) - 1))
    return tuple(out)


def view_sessions(employee_id: str, from_utc: dt.datetime, to_utc: dt.datetime,
                  ports: EnginePorts) -> tuple[SessionView, ...]:
    marks = ports.punch.marks_between(employee_id, from_utc, to_utc)      # [from, to)
    opening = ports.punch.last_mark_before(employee_id, from_utc)          # строго <
    closing = ports.punch.first_mark_after(employee_id, to_utc)            # первая ≥ to
    # чередование проверяет само ядро (CHK-PUNCH-SEQUENCE, R31); opening «ушёл» и
    # closing «пришёл» игнорируются ядром (R32)
    sessions = pair_marks(marks, opening, closing)
    return _views(employee_id, sessions, opening, closing)
