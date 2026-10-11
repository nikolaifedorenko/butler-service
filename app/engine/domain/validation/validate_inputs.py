"""Композиция стадии 1 (6.3): все правила уровня 2 в нормативном порядке; расчёт
не запускается, частичных результатов нет (RUL-INPUT-VALIDATION)."""
from __future__ import annotations

import datetime as dt
from typing import Sequence

from ..settings.types import Settings
from ..types.entities import Adjustment, Day, DeferredBlock, Period
from .check_close_allowed import check_close_allowed
from .check_day_values import check_day_values
from .check_groups import check_groups
from .check_known_day_codes import check_known_day_codes
from .check_now_in_period import check_now_in_period
from .check_opening_inputs import check_opening_inputs
from .check_period_bounds import check_period_bounds
from .check_plan_minutes import check_plan_minutes
from .check_timesheet_covers_period import check_timesheet_covers_period


def validate_inputs(period: Period, days: Sequence[Day], adjustments: Sequence[Adjustment],
                    deferred_in: Sequence[DeferredBlock], st: Settings, now: dt.datetime,
                    mode: str, previous_step_minutes: int) -> None:
    """Отметки на стадии 1 не проверяются: их нет во входе стадии (5.3); чередование
    проверяет ядро pair_marks на стадии 4 (CHK-PUNCH-SEQUENCE, v7/R31)."""
    check_period_bounds(period)
    check_known_day_codes(days, st)
    check_timesheet_covers_period(days, period)
    check_day_values(days, st)
    check_plan_minutes(days, st)
    check_groups(days, st)
    check_opening_inputs(deferred_in, adjustments, period, previous_step_minutes)
    check_now_in_period(period, now, st)
    check_close_allowed(period, now, mode, st)
