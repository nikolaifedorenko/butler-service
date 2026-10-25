"""close_period (7.2–7.3): проверки до домена (отказ — типизированное исключение
application), затем settle(mode="close") + evaluate_flags и атомарное сохранение
в одной транзакции: результат, снимок флагов, закрывающий банк, исходящие переносы,
ClosingInputs, версии настроек, состояние периода. Любое исключение домена →
ничего не сохраняется; повторное и конкурентное закрытие невозможно.

check_close — предпроверка «всё или ничего» (решение владельца 25.10.2026: период
закрывается сразу у всего штата): те же шаги без блокировки и записи — отказ той же
ошибкой, что дало бы закрытие."""
from __future__ import annotations

import datetime as dt

from ..domain.types.entities import Period
from ..domain.validation.check_close_allowed import check_close_allowed
from ..ports.unit_of_work import StorageConflictError
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


def _compute(employee_id: str, period: Period, effective: Period, now: dt.datetime,
             ports: EnginePorts):
    _require_right(employee_id, period, ports)
    inp = load_inputs(employee_id, period, ports)
    check_close_allowed(effective, now, "close", inp.st)      # домен не вызывается (7.2)
    return inp, run_pipeline(inp, now, "close")


def check_close(employee_id: str, period: Period, now: dt.datetime,
                ports: EnginePorts) -> PeriodView:
    """Закрылся бы период: тот же расчёт, что close_period, ничего не сохраняется."""
    employment = ports.employment.employment(employee_id, period)
    effective = require_effective(employee_id, period, employment)
    return _compute(employee_id, period, effective, now, ports)[1]


def close_period(employee_id: str, period: Period, now: dt.datetime,
                 ports: EnginePorts) -> PeriodView:
    employment = ports.employment.employment(employee_id, period)
    effective = require_effective(employee_id, period, employment)
    _require_right(employee_id, period, ports)
    try:
        with ports.unit_of_work():
            # вход читается и результат пишется под одной блокировкой сотрудника: правка
            # отметок/Табеля/Графика/банка ждёт закрытия и не теряется между чтением и
            # сохранением (рецензия аудита 22.10.2026, TOCTOU)
            ports.store.lock_employee(employee_id)
            # повторная проверка права внутри — конкурентное закрытие
            inp, view = _compute(employee_id, period, effective, now, ports)
            ports.store.save_result(employee_id, period, view.settle, view.flags,
                                    inp.snapshot, inp.st.versions, inp.st.step_minutes)
            ports.bank_write.save_closing_bank(employee_id, period, view.settle.bank_closed_minutes)
            ports.carry_over.save_deferred(
                employee_id, next_period(period, inp.st.period_granularity),
                view.settle.deferred_blocks)
    except StorageConflictError as exc:
        # Оптимистическая конкурентность (7.3): повторная проверка права — check-then-act,
        # настоящую гонку закрывает уникальный ключ (сотрудник, период). Соперник успел
        # закоммититься между нашей проверкой и flush — период закрыт ДРУГОЙ транзакцией;
        # UoW откатил наши записи (атомарность, тест-план 15). Типизированный конфликт
        # состояния → 409 (найдено ревью 20.10.2026, P1-ts-1: раньше — IntegrityError → 500).
        raise PeriodAlreadyClosedError(f"{employee_id}:{period.start}") from exc
    return view
