"""free_capacity(card, codes, st) — ёмкость дня для переносов (v7/R13, CFG-PLACEMENT):
лимит − длина окна значения − Σ размещённых кодов; у значения без окна длина окна = 0.
Окно — из st.windows[card.timesheet_value] (не из card.plan_minutes: при «План=Факт»
план обнулён, а ёмкость остаётся от окна — EX-36 контроль)."""
from __future__ import annotations

from ..settings.types import Settings
from ..types.results import DayCard
from .codes import Codes


def free_capacity(card: DayCard, codes: Codes, st: Settings) -> int:
    window = st.windows.get(card.timesheet_value)
    length = window.length if window is not None else 0
    return max(0, st.day_limit_minutes - length - codes.placed_total(card.day))
