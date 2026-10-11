"""recalculate (7.2, v7/R28): только ПОСЛЕДНИЙ закрытый период; запрещён, если следующий
уже закрыт. Старт — с исходных ClosingInputs; отметки, Табель и корректировки
перечитываются свежими; сохранение ЗАМЕНЯЕТ результат, банк, переносы и снимок флагов;
ClosingInputs не перезаписываются; исчезнувшие переносы удаляются из входа следующего
периода (save_deferred заменяет)."""
from __future__ import annotations

import datetime as dt

from ..domain.types.entities import Period
from ._pipeline import run_pipeline
from .context import EnginePorts
from .employment import require_effective
from .errors import PeriodNotClosedError, RecalculationForbiddenError
from .load_inputs import load_inputs
from .months import next_period
from .period_view import PeriodView


def recalculate(employee_id: str, period: Period, now: dt.datetime,
                ports: EnginePorts) -> PeriodView:
    employment = ports.employment.employment(employee_id, period)
    require_effective(employee_id, period, employment)
    state = ports.store.period_state(employee_id, period)
    if not state.closed:
        raise PeriodNotClosedError(f"{employee_id}:{period.start}")
    if state.next_closed:
        raise RecalculationForbiddenError(f"{employee_id}:{period.start}")
    frozen = ports.store.closing_inputs(employee_id, period)
    if frozen is None:
        raise PeriodNotClosedError(f"{employee_id}:{period.start}")
    inp = load_inputs(employee_id, period, ports, frozen=frozen)
    with ports.unit_of_work():
        view = run_pipeline(inp, now, "close")
        ports.store.save_result(employee_id, period, view.settle, view.flags,
                                frozen, inp.st.versions, inp.st.step_minutes)
        ports.bank_write.save_closing_bank(employee_id, period, view.settle.bank_closed_minutes)
        ports.carry_over.save_deferred(
            employee_id, next_period(period, inp.st.period_granularity),
            view.settle.deferred_blocks)
    return view
