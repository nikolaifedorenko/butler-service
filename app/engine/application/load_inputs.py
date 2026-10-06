"""Сбор входа из портов, включая выборку отметок 7.4."""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from zoneinfo import ZoneInfo

from ..domain.settings.types import Settings
from ..domain.types.entities import Absence, Adjustment, Day, DeferredBlock, Mark, Period, Shift
from ..ports.settlement_store import ClosingInputs
from .context import EnginePorts


@dataclass(frozen=True)
class Inputs:
    period: Period
    days: tuple[Day, ...]
    marks: tuple[Mark, ...]
    opening_mark: Mark | None
    bank_open: int
    adjustments: tuple[Adjustment, ...]
    deferred_in: tuple[DeferredBlock, ...]
    st: Settings
    previous_step: int
    shifts: tuple[Shift, ...]
    absences: tuple[Absence, ...]

    @property
    def snapshot(self) -> ClosingInputs:
        return ClosingInputs(self.bank_open, self.deferred_in, self.previous_step)


def punch_window(period: Period, st: Settings) -> tuple[dt.datetime, dt.datetime]:
    """7.4: локальная 00:00 period.start − step … локальная 00:00 (period.end + 1) + step, в UTC."""
    tz, step = ZoneInfo(st.tz), dt.timedelta(minutes=st.step_minutes)
    lo = dt.datetime.combine(period.start, dt.time(0), tz) - step
    hi = dt.datetime.combine(period.end + dt.timedelta(days=1), dt.time(0), tz) + step
    return lo.astimezone(dt.timezone.utc), hi.astimezone(dt.timezone.utc)


def load_inputs(employee_id: str, period: Period, ports: EnginePorts,
                snapshot: ClosingInputs | None = None) -> Inputs:
    st = ports.settings.load(period)
    lo, hi = punch_window(period, st)
    prev = ports.store.previous_step(employee_id, period) or st.step_minutes
    snap = snapshot or ClosingInputs(ports.bank.opening(employee_id, period),
                                     tuple(ports.carry_over.load_deferred(employee_id, period)), prev)
    return Inputs(period=period, days=tuple(ports.timesheet.days(employee_id, period)),
                  marks=tuple(ports.punch.marks_between(employee_id, lo, hi)),
                  opening_mark=ports.punch.last_mark_before(employee_id, lo),
                  bank_open=snap.bank_open_minutes, adjustments=tuple(ports.bank.adjustments(employee_id, period)),
                  deferred_in=tuple(snap.deferred_in), st=st, previous_step=snap.previous_step_minutes,
                  shifts=tuple(ports.shift.shifts(employee_id, period)),
                  absences=tuple(ports.absence.absences(employee_id, period)))
