"""view_period (7.1–7.2): закрытый период — чтение сохранённых SettleResult и снимка
FlagsResult без пересчёта (RUL-CLOSED-PERIOD-IMMUTABLE); незакрытый — живой расчёт
mode="view", ничего не сохраняется; отклонение при незакрытом предшественнике
(RUL-VIEW-AFTER-PREVIOUS) и вне трудоустройства (v7.1/R35)."""
from __future__ import annotations

import datetime as dt

from ..domain.types.entities import Period
from ._pipeline import run_pipeline
from .context import EnginePorts
from .employment import require_effective
from .errors import PreviousPeriodNotClosedError
from .load_inputs import load_inputs
from .period_view import PeriodView


def view_period(employee_id: str, period: Period, now: dt.datetime,
                ports: EnginePorts) -> PeriodView:
    employment = ports.employment.employment(employee_id, period)
    require_effective(employee_id, period, employment)
    state = ports.store.period_state(employee_id, period)
    days = tuple(ports.timesheet.days(employee_id, period))
    if state.closed:
        saved = ports.store.load_result(employee_id, period)
        return PeriodView(saved[0], saved[1], employment, days)
    if not state.previous_closed and not state.opening_bank_set:
        raise PreviousPeriodNotClosedError(f"{employee_id}:{period.start}")
    return run_pipeline(load_inputs(employee_id, period, ports), now, "view")
