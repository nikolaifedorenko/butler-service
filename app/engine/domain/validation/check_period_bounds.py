"""CHK-PERIOD-BOUNDS (v7.1): Period.start ≤ Period.end (3.3)."""
from __future__ import annotations

from ..types.entities import Period
from ..types.errors import InvalidInputDataError


def check_period_bounds(period: Period) -> None:
    if period.start > period.end:
        raise InvalidInputDataError("CHK-PERIOD-BOUNDS",
                                    {"start": period.start, "end": period.end})
