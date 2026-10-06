from dataclasses import dataclass
from typing import Protocol, Sequence

from ..domain.types.entities import DeferredBlock, Period
from ..domain.types.results import SettleResult


@dataclass(frozen=True)
class ClosingInputs:
    """Входной снимок закрытия: по нему выполняется пересчёт (7.3)."""
    bank_open_minutes: int
    deferred_in: tuple[DeferredBlock, ...]
    previous_step_minutes: int


@dataclass(frozen=True)
class PeriodState:
    closed: bool
    next_closed: bool


class SettlementStorePort(Protocol):
    def save_result(self, employee_id: str, period: Period, result: SettleResult,
                    inputs_snapshot: ClosingInputs, settings_versions: Sequence[str], step_minutes: int,
                    replace: bool) -> None: ...
    def period_state(self, employee_id: str, period: Period) -> PeriodState: ...
    def closing_inputs(self, employee_id: str, period: Period) -> ClosingInputs | None: ...
    def previous_step(self, employee_id: str, period: Period) -> int | None: ...
