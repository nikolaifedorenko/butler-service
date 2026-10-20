"""close_period (7.2–7.3): проверки до домена (отказ — типизированное исключение
application), затем settle(mode="close") + evaluate_flags и атомарное сохранение
в одной транзакции: результат, снимок флагов, закрывающий банк, исходящие переносы,
ClosingInputs, версии настроек, состояние периода. Любое исключение домена →
ничего не сохраняется; повторное и конкурентное закрытие невозможно."""
from __future__ import annotations

import datetime as dt

from ..domain.types.entities import Period
from ..domain.validation.check_close_allowed import check_close_allowed
from ._pipeline import run_pipeline
from .context import EnginePorts
from .employment import require_effective
from .errors import PeriodAlreadyClosedError, PreviousPeriodNotClosedError
from .load_inputs import load_inputs
from .months import next_period
from .period_view import PeriodView


def _require_right(employee_id: str, period: Period, ports: EnginePorts) -> None:
    state = ports.store.period_state(employee_id, period)
    if state.closed:
        raise PeriodAlreadyClosedError(f"{employee_id}:{period.start}")
    if not state.previous_closed and not state.opening_bank_set:
        raise PreviousPeriodNotClosedError(f"{employee_id}:{period.start}")


def close_period(employee_id: str, period: Period, now: dt.datetime,
                 ports: EnginePorts) -> PeriodView:
    employment = ports.employment.employment(employee_id, period)
    effective = require_effective(employee_id, period, employment)
    _require_right(employee_id, period, ports)
    inp = load_inputs(employee_id, period, ports)
    check_close_allowed(effective, now, "close", inp.st)      # домен не вызывается (7.2)
    with ports.unit_of_work():
        _require_right(employee_id, period, ports)            # конкурентное закрытие
        view = run_pipeline(inp, now, "close")
        ports.store.save_result(employee_id, period, view.settle, view.flags,
                                inp.snapshot, inp.st.versions, inp.st.step_minutes)
        ports.bank_write.save_closing_bank(employee_id, period, view.settle.bank_closed_minutes)
        ports.carry_over.save_deferred(
            employee_id, next_period(period, inp.st.period_granularity),
            view.settle.deferred_blocks)
    return view
