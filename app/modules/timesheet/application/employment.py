"""Эффективный период (7.1, v7/R23, R35): пересечение запрошенного периода с интервалом
трудоустройства; домен о трудоустройстве не знает."""
from __future__ import annotations

from ..domain.types.entities import Employment, Period
from .errors import PeriodOutsideEmploymentError


def effective_period(period: Period, employment: Employment) -> Period | None:
    """None — пересечение пусто (период целиком вне трудоустройства)."""
    start = max(period.start, employment.start)
    end = period.end if employment.end is None else min(period.end, employment.end)
    return Period(start, end) if start <= end else None


def require_effective(employee_id: str, period: Period, employment: Employment) -> Period:
    effective = effective_period(period, employment)
    if effective is None:
        raise PeriodOutsideEmploymentError(employee_id, period)
    return effective
