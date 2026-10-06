"""Входные доменные сущности (3.2)."""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Literal

Minutes = int
Mode = Literal["view", "close"]
PresenceState = Literal["open", "closed"]
OPEN: PresenceState = "open"
CLOSED: PresenceState = "closed"
KIND_IN = "in"
KIND_OUT = "out"


@dataclass(frozen=True)
class Period:
    start: dt.date
    end: dt.date


@dataclass(frozen=True)
class Day:
    day: dt.date
    code: str
    plan_minutes: Minutes
    employee_id: str
    group: str


@dataclass(frozen=True)
class Mark:
    employee_id: str
    at_utc: dt.datetime
    kind: Literal["in", "out"]


@dataclass(frozen=True)
class CalcMark:
    source: Mark
    at_calc: dt.datetime
    day: dt.date


@dataclass(frozen=True)
class Interval:
    day: dt.date
    start_minute: Minutes
    end_minute: Minutes

    @property
    def length(self) -> Minutes:
        return max(0, self.end_minute - self.start_minute)


@dataclass(frozen=True)
class Shift:
    employee_id: str
    start_utc: dt.datetime
    end_utc: dt.datetime


@dataclass(frozen=True)
class Absence:
    employee_id: str
    day: dt.date
    start_minute: Minutes
    end_minute: Minutes


@dataclass(frozen=True)
class Adjustment:
    amount_minutes: Minutes
    reason_code: str
    note: str | None = None


@dataclass(frozen=True)
class DeferredBlock:
    source_day: dt.date
    tariff: str
    minutes: Minutes
    reason_code: str
