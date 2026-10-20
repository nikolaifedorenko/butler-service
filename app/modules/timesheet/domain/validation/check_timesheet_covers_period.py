"""CHK-DAYS-IN-PERIOD и CHK-TIMESHEET-COVERS (5.3, RUL-TIMESHEET-COVERS-PERIOD):
в days нет строк вне периода; на каждый день периода ровно одна строка Табеля.
Табель читается полным запрошенным периодом (v7/R27) — строки вне эффективного
периода отбраковываются здесь (EX-55 к.1)."""
from __future__ import annotations

from typing import Sequence

from ..time.period_days import period_days
from ..types.entities import Day, Period
from ..types.errors import IncompleteTimesheetError, InvalidInputDataError


def check_timesheet_covers_period(days: Sequence[Day], period: Period) -> None:
    outside = sorted(d.day for d in days if not (period.start <= d.day <= period.end))
    if outside:
        raise InvalidInputDataError("CHK-DAYS-IN-PERIOD", {"days_outside_period": tuple(outside)})
    counts: dict = {}
    for d in days:
        counts[d.day] = counts.get(d.day, 0) + 1
    missing = tuple(day for day in period_days(period) if day not in counts)
    duplicated = tuple(day for day, n in sorted(counts.items()) if n > 1)
    if missing or duplicated:
        raise IncompleteTimesheetError(missing, duplicated)
