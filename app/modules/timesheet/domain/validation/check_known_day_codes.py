"""CHK-DAY-CODE-KNOWN: каждый код дня есть в CFG-DAY-CODES (5.3) → UnknownDayCodeError."""
from __future__ import annotations

from typing import Sequence

from ..settings.types import Settings
from ..types.entities import Day
from ..types.errors import UnknownDayCodeError


def check_known_day_codes(days: Sequence[Day], st: Settings) -> None:
    for day in sorted(days, key=lambda d: d.day):
        if day.code not in st.day_code_policy:
            raise UnknownDayCodeError(day.code, day.day)
