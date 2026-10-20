"""ScheduleStorePort (7.3, 16.3): хранилище Графика — записи ShiftEntry(shift, source).
Смены физически не режутся (v7/R17): «разрез» — логический, через записи согласованных
отсутствий. save_absence/drop_absence — точка ввода отсутствий (5.1: UI вводит дату и
интервал HH:MM–HH:MM, в том числе с переходом на следующие сутки; адаптер конвертирует
в UTC-интервал)."""
from __future__ import annotations

import datetime as dt
from typing import Protocol, Sequence

from ..domain.types.entities import Period, Shift, ShiftEntry


class ScheduleStorePort(Protocol):
    def load_entries(self, employee_id: str | None, period: Period) -> Sequence[ShiftEntry]: ...
    def save_manual(self, employee_id: str, day: dt.date, shifts: Sequence[Shift]) -> None: ...
    def drop_manual(self, employee_id: str, day: dt.date) -> None: ...
    def replace_generated(self, employee_id: str, period: Period,
                          entries: Sequence[ShiftEntry]) -> None: ...
    def save_absence(self, employee_id: str, day: dt.date, start_hhmm: str, end_hhmm: str,
                     end_next_day: bool) -> int: ...
    def drop_absence(self, absence_id: int) -> None: ...
