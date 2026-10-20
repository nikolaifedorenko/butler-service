"""present_at(raw_intervals, moment_utc) — состояние присутствия в момент (4.3, v7/R29):
момент лежит внутри некоторой сессии, start ≤ t < end — «строго» только про конец;
приход ровно в start считается присутствием."""
from __future__ import annotations

import datetime as dt
from typing import Sequence

from ..types.entities import RawInterval


def present_at(raw_intervals: Sequence[RawInterval], moment_utc: dt.datetime) -> bool:
    return any(iv.start_utc <= moment_utc < iv.end_utc for iv in raw_intervals)
