from typing import Protocol, Sequence

from ..domain.types.entities import Absence, Period


class AbsencePort(Protocol):        # График: согласованные отсутствия
    def absences(self, employee_id: str, period: Period) -> Sequence[Absence]: ...
