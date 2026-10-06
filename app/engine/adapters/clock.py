"""ClockPort: системное время (единственное место чтения «сейчас» для движка)."""
from __future__ import annotations

import datetime as dt


class SystemClock:
    def now(self) -> dt.datetime:
        return dt.datetime.now(dt.timezone.utc)


class FixedClock:
    def __init__(self, at: dt.datetime):
        self.at = at

    def now(self) -> dt.datetime:
        return self.at
