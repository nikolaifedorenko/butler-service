"""EmploymentPort (2.6, v7/R23, v7.1/R38): интервал трудоустройства — используется
только application (эффективный период); active_employees — батч популяции доски."""
from __future__ import annotations

import datetime as dt
from typing import Protocol, Sequence

from ..domain.types.entities import Employment, Period


class EmploymentPort(Protocol):
    def employment(self, employee_id: str, period: Period) -> Employment: ...
    def active_employees(self, on_day: dt.date) -> Sequence[str]: ...
