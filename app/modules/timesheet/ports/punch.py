"""PunchPort (2.6, 7.4): UTC-aware отметки, стабильный порядок, допустимое чередование
(первая линия; вторая — ядро pair_marks), отметок позже now нет.

Границы выборок (v7/R7): marks_between = [from, to); last_mark_before — строго <;
first_mark_after — первая ≥ to; last_marks — ≤ at."""
from __future__ import annotations

import datetime as dt
from typing import Protocol, Sequence

from ..domain.types.entities import Mark


class PunchPort(Protocol):
    def marks_between(self, employee_id: str, from_utc: dt.datetime,
                      to_utc: dt.datetime) -> Sequence[Mark]: ...
    def last_mark_before(self, employee_id: str, at_utc: dt.datetime) -> Mark | None: ...
    def first_mark_after(self, employee_id: str, at_utc: dt.datetime) -> Mark | None: ...
    def last_marks(self, at_utc: dt.datetime) -> Sequence[Mark]: ...
    def prefetch(self, employee_ids: Sequence[str], from_utc: dt.datetime,
                 to_utc: dt.datetime) -> None:
        """Подготовить marks_between/last_mark_before этого окна для многих сотрудников сразу
        (экраны на весь штат, PERF-02). Результаты методов не меняются."""
        ...
