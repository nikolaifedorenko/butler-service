"""Точка ввода ручных корректировок банка (7.2, v7.1/R37): посев OPENING_SEED — только
для первого периода сотрудника; корректировки закрытого периода отклоняются (правка —
через recalculate). Ядро маркер не интерпретирует (RUL-REASON-CODE-FREE) — распознавание
OPENING_SEED здесь и в адаптерах (PeriodState.opening_bank_set)."""
from __future__ import annotations

import datetime as dt

from ..domain.types.entities import Period
from .context import EnginePorts
from .errors import AdjustmentClosedPeriodError, SeedNotAllowedError
from .months import is_first_period, period_containing

OPENING_SEED = "OPENING_SEED"          # конвенция адаптера (v7.1/R37), не код домена


def validate_adjustment_entry(employee_id: str, day: dt.date, reason_code: str,
                              ports: EnginePorts) -> Period:
    """Возвращает период внесения корректировки; бросает типизированные ошибки."""
    st = ports.settings.load(period_containing(day, "month"))
    prd = period_containing(day, st.period_granularity)
    if ports.store.period_state(employee_id, prd).closed:
        raise AdjustmentClosedPeriodError(f"{employee_id}:{prd.start}")
    if reason_code == OPENING_SEED:
        employment = ports.employment.employment(employee_id, prd)
        if not is_first_period(prd, employment, st.period_granularity):
            raise SeedNotAllowedError(f"{employee_id}:{prd.start}")
    return prd
