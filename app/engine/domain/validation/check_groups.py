"""CHK-SINGLE-EMPLOYEE и CHK-GROUP-EXISTS (5.3): все строки одного сотрудника (группа
может различаться по дням — RUL-GROUP-PER-DAY); группа каждой строки существует
в CFG-GROUPS."""
from __future__ import annotations

from typing import Sequence

from ..settings.types import Settings
from ..types.entities import Day
from ..types.errors import InvalidInputDataError


def check_groups(days: Sequence[Day], st: Settings) -> None:
    employees = {d.employee_id for d in days}
    if len(employees) > 1:
        raise InvalidInputDataError("CHK-SINGLE-EMPLOYEE", {"employees": tuple(sorted(employees))})
    unknown = tuple(sorted({d.group for d in days} - set(st.groups)))
    if unknown:
        raise InvalidInputDataError("CHK-GROUP-EXISTS", {"groups": unknown})
