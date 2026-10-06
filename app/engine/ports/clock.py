import datetime as dt
from typing import Protocol


class ClockPort(Protocol):
    def now(self) -> dt.datetime: ...   # UTC-aware
