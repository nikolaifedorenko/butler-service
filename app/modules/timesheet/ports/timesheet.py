"""TimesheetPort (2.6): ровно одна строка на каждый день периода; UTC-независимо.
Вызывается ПОЛНЫМ запрошенным периодом даже при сужении до трудоустройства (v7/R27) —
строки вне трудоустройства отбраковывает домен (CHK-DAYS-IN-PERIOD, EX-55 к.1)."""
from __future__ import annotations

import datetime as dt
from typing import Mapping, Protocol, Sequence

from ..domain.types.entities import Day, Period


class TimesheetPort(Protocol):
    def days(self, employee_id: str, period: Period) -> Sequence[Day]: ...
    def codes_for(self, employee_ids: Sequence[str], period: Period) -> Mapping[tuple[str, dt.date], str]: ...
