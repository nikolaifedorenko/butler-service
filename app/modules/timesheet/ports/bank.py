"""BankPort (2.6): непрерывность банка — opening(P) = closing(P−1); для первого периода
сотрудника 0, начальное значение — посевающая корректировка OPENING_SEED (v7.1/R37).
Только корректировки своего периода (RUL-BANK-CONTINUITY)."""
from __future__ import annotations

from typing import Protocol, Sequence

from ..domain.types.entities import Adjustment, Minutes, Period


class BankPort(Protocol):
    def opening(self, employee_id: str, period: Period) -> Minutes: ...
    def adjustments(self, employee_id: str, period: Period) -> Sequence[Adjustment]: ...
