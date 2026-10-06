from typing import Protocol, Sequence

from ..domain.types.entities import Adjustment, Period


class BankPort(Protocol):
    def opening(self, employee_id: str, period: Period) -> int: ...
    def adjustments(self, employee_id: str, period: Period) -> Sequence[Adjustment]: ...
