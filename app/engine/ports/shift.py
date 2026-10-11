"""ShiftPort (2.6): контракт выборки (v7.1/F-04) — все смены, пересекающие
[00:00 period.start, 00:00 period.end+1), включая начинающиеся до периода.
Валидация уровня 3 (CHK-SHIFT-ORDER) — в адаптере при чтении."""
from __future__ import annotations

import datetime as dt
from typing import Protocol, Sequence

from ..domain.types.entities import Period, Shift


class ShiftPort(Protocol):
    def shifts(self, employee_id: str, period: Period) -> Sequence[Shift]: ...
    def shifts_on_day(self, day: dt.date) -> Sequence[Shift]: ...
