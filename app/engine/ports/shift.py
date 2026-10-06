from typing import Protocol, Sequence

from ..domain.types.entities import Period, Shift


class ShiftPort(Protocol):          # График: смены
    def shifts(self, employee_id: str, period: Period) -> Sequence[Shift]: ...
