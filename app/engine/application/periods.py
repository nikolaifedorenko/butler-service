"""Понятие «следующий период» определяется в application (3.3): период — календарный месяц."""
from __future__ import annotations

import datetime as dt

from ..domain.types.entities import Period


def month_period(year: int, month: int) -> Period:
    nxt = dt.date(year + (month == 12), month % 12 + 1, 1)
    return Period(dt.date(year, month, 1), nxt - dt.timedelta(days=1))


def next_period(period: Period) -> Period:
    return month_period((period.end + dt.timedelta(days=1)).year, (period.end + dt.timedelta(days=1)).month)


def previous_period(period: Period) -> Period:
    prev_end = period.start - dt.timedelta(days=1)
    return month_period(prev_end.year, prev_end.month)
