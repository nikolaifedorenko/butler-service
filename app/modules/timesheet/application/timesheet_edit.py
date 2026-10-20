"""Вкладка «Табель» (16.5): запись строки с валидацией ТЕМИ ЖЕ доменными проверочными
функциями (check_known_day_codes, check_plan_minutes, check_day_values — v7.1/F-16;
вторые копии правил на стороне записи запрещены); редактируемость периода; после
сохранения дня D — перегенерация Графика дня D (16.3). Пересчёт часов не запускается."""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from ..domain.types.entities import Day, Period
from ..domain.validation.check_day_values import check_day_values
from ..domain.validation.check_known_day_codes import check_known_day_codes
from ..domain.validation.check_plan_minutes import check_plan_minutes
from .context import EnginePorts
from .errors import TimesheetLockedError, TimesheetOutsideEmploymentError
from .months import period_containing
from .schedule_view import rebuild_generated_schedule


@dataclass(frozen=True)
class TimesheetEditOutcome:
    needs_recalculate: bool        # период — последний закрытый: правка видна через пересчёт
    manual_shifts_dropped: tuple[dt.date, ...]


def lock_state(employee_id: str, day: dt.date, ports: EnginePorts) -> str:
    """open — свободная правка; last_closed — с предупреждением; locked — только чтение."""
    st = ports.settings.load(period_containing(day, "month"))
    prd = period_containing(day, st.period_granularity)
    state = ports.store.period_state(employee_id, prd)
    if not state.closed:
        return "open"
    return "locked" if state.next_closed else "last_closed"


def save_timesheet_day(employee_id: str, day: dt.date, code: str, plan_minutes: int | None,
                       ports: EnginePorts, *, rebuild: bool = True) -> TimesheetEditOutcome:
    """Запись ячейки Табеля (доменные проверки F-16) + перегенерация Графика дня.

    `rebuild=False` — режим массовой операции (P0-3 ревью 20.10.2026): перегенерация
    Графика на каждую ячейку — это DELETE+INSERT generated-строк на каждый день, то
    есть сотни тысяч запросов на массовке 500×366. Вызывающий код ОБЯЗАН после записи
    всех ячеек вызвать `schedule_view.rebuild_generated_for_days` по записанным дням:
    без этого График останется stale. `manual_shifts_dropped` в таком режиме пуст —
    удалённые ручные смены возвращает пакетная перегенерация.
    """
    employment = ports.employment.employment(employee_id, Period(day, day))
    if day < employment.start or (employment.end is not None and day > employment.end):
        raise TimesheetOutsideEmploymentError(f"{employee_id}:{day}")
    if lock_state(employee_id, day, ports) == "locked":
        raise TimesheetLockedError(f"{employee_id}:{day}")
    st = ports.settings.load(period_containing(day, "month"))
    if code != "":
        row = Day(day, code, plan_minutes or 0, employee_id, "")
        check_known_day_codes([row], st)
        check_plan_minutes([row], st)
        check_day_values([row], st)
    ports.timesheet_store.save_day(employee_id, day, code, plan_minutes)
    dropped: tuple[dt.date, ...] = ()
    if rebuild:
        # перегенерация дня D и соседей: смена через полночь даёт отрезки двум дням (16.3)
        outcome = rebuild_generated_schedule(
            employee_id, Period(day - dt.timedelta(days=1), day + dt.timedelta(days=1)), ports)
        dropped = outcome.manual_dropped
    return TimesheetEditOutcome(lock_state(employee_id, day, ports) == "last_closed", dropped)
