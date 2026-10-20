"""Сбор входа из портов, включая выборку отметок 7.4: запас в шаг за границами
эффективного периода + opening_mark; Табель — ПОЛНЫМ запрошенным периодом (v7/R27)."""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from ..domain.settings.types import Settings
from ..domain.types.entities import (
    Absence,
    Adjustment,
    ClosingInputs,
    Day,
    DeferredBlock,
    Employment,
    Mark,
    Period,
    Shift,
)
from .context import EnginePorts
from .employment import require_effective
from .months import is_first_period, previous_period


@dataclass(frozen=True)
class Inputs:
    requested: Period                 # запрошенный период UI
    period: Period                    # эффективный период (∩ трудоустройство)
    days: tuple[Day, ...]             # строки Табеля ПОЛНОГО запрошенного периода (R27)
    marks: tuple[Mark, ...]
    opening_mark: Mark | None
    bank_open: int
    adjustments: tuple[Adjustment, ...]
    deferred_in: tuple[DeferredBlock, ...]
    st: Settings
    previous_step: int
    shifts: tuple[Shift, ...]
    absences: tuple[Absence, ...]
    employment: Employment

    @property
    def snapshot(self) -> ClosingInputs:
        return ClosingInputs(self.bank_open, self.deferred_in, self.previous_step)


def punch_window(period: Period, st: Settings) -> tuple[dt.datetime, dt.datetime]:
    """7.4: from = локальная 00:00 period.start − step → UTC;
    to = локальная 00:00 (period.end + 1) + step → UTC."""
    step = dt.timedelta(minutes=st.step_minutes)
    lo = dt.datetime.combine(period.start, dt.time(0), st.tz) - step
    hi = dt.datetime.combine(period.end + dt.timedelta(days=1), dt.time(0), st.tz) + step
    return lo.astimezone(dt.timezone.utc), hi.astimezone(dt.timezone.utc)


def _previous_step(effective: Period, employment: Employment, st: Settings,
                   ports: EnginePorts) -> int:
    """7.4: шаг предыдущего периода цепочки; для первого периода — текущий шаг (2.6)."""
    if is_first_period(effective, employment, st.period_granularity):
        return st.step_minutes
    prev = previous_period(effective, st.period_granularity)
    return ports.settings.load(prev).step_minutes


def load_inputs(employee_id: str, period: Period, ports: EnginePorts,
                frozen: ClosingInputs | None = None) -> Inputs:
    """Отметки, Табель и корректировки — всегда свежие из портов (v7/R28);
    заморожены только ClosingInputs (при recalculate)."""
    st = ports.settings.load(period)
    employment = ports.employment.employment(employee_id, period)
    effective = require_effective(employee_id, period, employment)
    days = tuple(ports.timesheet.days(employee_id, period))
    from_utc, to_utc = punch_window(effective, st)
    snapshot = frozen or ClosingInputs(
        ports.bank.opening(employee_id, effective),
        tuple(ports.carry_over.load_deferred(employee_id, effective)),
        _previous_step(effective, employment, st, ports))
    return Inputs(
        requested=period, period=effective, days=days,
        marks=tuple(ports.punch.marks_between(employee_id, from_utc, to_utc)),
        opening_mark=ports.punch.last_mark_before(employee_id, from_utc),
        bank_open=snapshot.bank_open,
        adjustments=tuple(ports.bank.adjustments(employee_id, effective)),
        deferred_in=tuple(snapshot.deferred_in), st=st,
        previous_step=snapshot.previous_step_minutes,
        shifts=tuple(ports.shift.shifts(employee_id, effective)),
        absences=tuple(ports.absence.absences(employee_id, effective)),
        employment=employment)
