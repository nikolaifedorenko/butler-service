from __future__ import annotations

from ..domain.types.entities import Period
from .compute import compute
from .context import EnginePorts
from .errors import PeriodAlreadyClosedError
from .load_inputs import load_inputs
from .period_view import PeriodView
from .periods import next_period


def close_period(employee_id: str, period: Period, ports: EnginePorts) -> PeriodView:
    """close: проверка права и атомарное сохранение результата, банка, переносов, снимка, версий."""
    with ports.unit_of_work():
        if ports.store.period_state(employee_id, period).closed:
            raise PeriodAlreadyClosedError(f"{employee_id}:{period.start}")
        inp = load_inputs(employee_id, period, ports)
        view = compute(inp, ports.clock.now(), "close", True)
        ports.store.save_result(employee_id, period, view.settle, inp.snapshot, inp.st.versions,
                                inp.st.step_minutes, replace=False)
        ports.bank_write.save_closing_bank(employee_id, period, view.settle.bank_closed_minutes)
        ports.carry_over.save_deferred(employee_id, next_period(period), view.settle.deferred_blocks)
    return view
