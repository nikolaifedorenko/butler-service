"""SettlementStorePort (7.3): атомарное сохранение результата и снимка флагов,
состояние периода (PeriodState — closed/previous_closed/next_closed/opening_bank_set,
v7/R26, R37)."""
from __future__ import annotations

from typing import Protocol, Sequence

from ..domain.types.entities import ClosingInputs, Period, PeriodState
from ..domain.types.results import FlagsResult, SettleResult


class SettlementStorePort(Protocol):
    def save_result(self, employee_id: str, period: Period, result: SettleResult,
                    flags: FlagsResult, inputs_snapshot: ClosingInputs,
                    settings_versions: Sequence[str], step_minutes: int = 60) -> None:
        """step_minutes — шаг периода (расширение адаптера: источник previous_step
        следующего периода цепочки, 7.4)."""
        ...
    def load_result(self, employee_id: str,
                    period: Period) -> tuple[SettleResult, FlagsResult] | None: ...
    def period_state(self, employee_id: str, period: Period) -> PeriodState: ...
    def lock_marks(self, employee_ids: Sequence[str],
                   period: Period) -> dict[str, tuple[bool, bool]]:
        """(closed, next_closed) из period_state для многих сотрудников сразу — экранам
        Табеля и Графика (без запросов на каждого сотрудника, PERF-02)."""
        ...
    def closing_inputs(self, employee_id: str, period: Period) -> ClosingInputs | None:
        """Входной снимок закрытия — основа recalculate (7.2, v7/R28: заморожены
        только ClosingInputs)."""
        ...
