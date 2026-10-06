from typing import Protocol, Sequence

from ..domain.types.entities import Day, Period


class TimesheetPort(Protocol):
    def days(self, employee_id: str, period: Period) -> Sequence[Day]: ...
