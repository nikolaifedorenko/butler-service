from typing import Protocol, Sequence

from ..domain.types.entities import DeferredBlock, Period


class CarryOverPort(Protocol):
    def load_deferred(self, employee_id: str, period: Period) -> Sequence[DeferredBlock]: ...
    def save_deferred(self, employee_id: str, next_period: Period, blocks: Sequence[DeferredBlock]) -> None: ...
