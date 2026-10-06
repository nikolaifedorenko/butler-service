"""Результаты расчёта (3.2)."""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Mapping

from .entities import DeferredBlock, Minutes


@dataclass(frozen=True)
class Reason:
    step: str
    code: str
    data: Mapping[str, object]


@dataclass(frozen=True)
class Flag:
    day: dt.date
    code: str
    data: Mapping[str, object]


@dataclass(frozen=True)
class Cut:
    source_day: dt.date
    placed_day: dt.date | None
    tariff: str
    taken_minutes: Minutes
    paid_minutes: Minutes


@dataclass(frozen=True)
class DayCard:
    day: dt.date
    timesheet_value: str
    plan_minutes: Minutes
    full_fact_minutes: Minutes
    work_minutes: Minutes
    overtime_minutes: Minutes
    debt_minutes: Minutes
    codes: Mapping[str, Minutes]
    pays_overtime: bool
    open_at_start: bool
    open_at_end: bool
    plan_equals_fact_applied: bool


@dataclass(frozen=True)
class SettleResult:
    cards: tuple[DayCard, ...]
    mgmt_timesheet: Mapping[dt.date, Mapping[str, Minutes]]
    bank_open_minutes: Minutes
    bank_open_normalized_minutes: Minutes
    bank_adjustments_minutes: Minutes
    bank_closed_minutes: Minutes
    credited_to_bank_minutes: Minutes
    paid_with_bank_minutes: Minutes
    total_debt_minutes: Minutes
    residual_debt_minutes: Minutes
    cuts: tuple[Cut, ...]
    deferred_blocks: tuple[DeferredBlock, ...]
    open_session_since_utc: dt.datetime | None
    exceptions: tuple[Reason, ...]
    trace: tuple[Reason, ...]


@dataclass(frozen=True)
class FlagsResult:
    flags: tuple[Flag, ...]
