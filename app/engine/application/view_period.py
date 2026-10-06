from __future__ import annotations

from ..domain.types.entities import Period
from .compute import compute
from .context import EnginePorts
from .load_inputs import load_inputs
from .period_view import PeriodView


def view_period(employee_id: str, period: Period, ports: EnginePorts) -> PeriodView:
    """view: ничего не сохраняет, доступен в любое время."""
    state = ports.store.period_state(employee_id, period)
    return compute(load_inputs(employee_id, period, ports), ports.clock.now(), "view", state.closed)


def preview_close(employee_id: str, period: Period, ports: EnginePorts) -> PeriodView:
    """Предпросмотр закрытия: тот же settle(mode="close"), но без сохранения."""
    snapshot = ports.store.closing_inputs(employee_id, period)
    inp = load_inputs(employee_id, period, ports, snapshot)
    return compute(inp, ports.clock.now(), "close", ports.store.period_state(employee_id, period).closed)
