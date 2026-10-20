"""period_days(period) — дни периода по возрастанию (3.3: Period — непрерывный диапазон)."""
from __future__ import annotations

import datetime as dt

from ..types.entities import Period


def period_days(period: Period) -> tuple[dt.date, ...]:
    count = (period.end - period.start).days + 1
    return tuple(period.start + dt.timedelta(days=i) for i in range(count))
