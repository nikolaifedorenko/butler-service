"""open_sessions(last_marks, now) — у кого последняя отметка «пришёл»: сессия открыта
(4.3, 16.2). Возвращает (employee_id, open_since_utc) по возрастанию момента; забытый
уход показывается как есть — доска ничего не «закрывает»."""
from __future__ import annotations

import datetime as dt
from typing import Sequence

from ..types.entities import KIND_IN, Mark


def open_sessions(last_marks: Sequence[Mark],
                  now: dt.datetime) -> tuple[tuple[str, dt.datetime], ...]:
    opened = [(m.employee_id, m.at_utc) for m in last_marks
              if m.kind == KIND_IN and m.at_utc <= now]
    return tuple(sorted(opened, key=lambda pair: (pair[1], pair[0])))
