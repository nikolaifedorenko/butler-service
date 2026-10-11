"""policy_of(day, st) — строка CFG-DAY-CODES кода дня; отсутствие строки — ошибка (2.8)."""
from __future__ import annotations

from ..settings.types import DayCodePolicy, Settings
from ..types.entities import Day
from ..types.errors import UnknownDayCodeError


def policy_of(day: Day, st: Settings) -> DayCodePolicy:
    policy = st.day_code_policy.get(day.code)
    if policy is None:
        raise UnknownDayCodeError(day.code, day.day)
    return policy
