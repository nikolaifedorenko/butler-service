"""CHK-WINDOW-EXISTS (5.3, 3.3): каждое значение Табеля, несущее часы, имеет строку
в CFG-WINDOWS → UnknownTimesheetValueError(value); расчёт не запускается.

Значения с некорректным планом (нулевым/отрицательным либо непредставимым — не кратным
15) пропускаются: их отбраковывает CHK-PLAN-CONSISTENT/CHK-PLAN-FORMAT той же стадии
(13 п.4: «Я 0» → CHK-PLAN-CONSISTENT, «Я 500» → CHK-PLAN-FORMAT); канонический ключ
для них непостроим либо несогласован с кодом (3.3)."""
from __future__ import annotations

from typing import Sequence

from ..day_card.policy_of import policy_of
from ..day_card.value_of import value_of
from ..settings.types import Settings
from ..types.entities import Day
from ..types.errors import UnknownTimesheetValueError


def _checkable(day: Day) -> bool:
    """План положителен и представим в нотации значения; иначе день — забота CHK-PLAN-*."""
    return day.plan_minutes > 0 and day.plan_minutes * 5 % 3 == 0


def check_day_values(days: Sequence[Day], st: Settings) -> None:
    for day in sorted(days, key=lambda r: r.day):
        if not policy_of(day, st).carries_hours or not _checkable(day):
            continue
        if value_of(day, st) not in st.windows:
            raise UnknownTimesheetValueError(value_of(day, st))
