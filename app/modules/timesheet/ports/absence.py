"""AbsencePort (2.6): все отсутствия, пересекающие период (v7.1), включая переходящие
границу. Валидация уровня 3 (CHK-ABSENCE-ORDER, CHK-ABSENCE-LENGTH ≤ 24 ч) — в адаптере;
CHK-ABSENCE-WITHIN-DAY удалён (v7/R17)."""
from __future__ import annotations

import datetime as dt
from typing import Protocol, Sequence

from ..domain.types.entities import Absence, Period


class AbsencePort(Protocol):
    def absences(self, employee_id: str, period: Period) -> Sequence[Absence]: ...
    def absences_on_day(self, day: dt.date) -> Sequence[Absence]: ...
    def absences_for(self, employee_ids: Sequence[str], period: Period) -> Sequence[Absence]: ...
