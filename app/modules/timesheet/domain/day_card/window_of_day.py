"""window_of_day(day, st) — строка CFG-WINDOWS значения Табеля; None = окна нет
(значение без часов: рабочее 0, весь факт — переработка, недостача 0; 3.3, RUL-WINDOW-FROM-TIMESHEET)."""
from __future__ import annotations

from ..settings.types import Settings, Window
from ..types.entities import Day
from .value_of import value_of


def window_of_day(day: Day, st: Settings) -> Window | None:
    return st.windows.get(value_of(day, st))
