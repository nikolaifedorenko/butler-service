"""Типизированные ошибки application (7.1–7.3): домен при их возникновении не вызывается."""
from __future__ import annotations

import datetime as dt


class ApplicationError(Exception):
    code = "APPLICATION_ERROR"


class PeriodOutsideEmploymentError(ApplicationError):
    """Запрошенный период целиком вне трудоустройства — не учитывается и не показывается
    (7.1, v7.1/R35); проверяется РАНЬШЕ всех прочих отказов."""

    code = "PERIOD_OUTSIDE_EMPLOYMENT"

    def __init__(self, employee_id: str, period):
        self.employee_id, self.period = employee_id, period
        super().__init__(f"{employee_id}: period {period.start}..{period.end} outside employment")


class PreviousPeriodNotClosedError(ApplicationError):
    """RUL-SEQUENTIAL-CLOSING / RUL-VIEW-AFTER-PREVIOUS: предыдущий период не закрыт
    и начальный банк не посеян (v7/R26, R37)."""

    code = "PREVIOUS_PERIOD_NOT_CLOSED"


class PeriodAlreadyClosedError(ApplicationError):
    code = "PERIOD_ALREADY_CLOSED"


class PeriodNotClosedError(ApplicationError):
    code = "PERIOD_NOT_CLOSED"


class RecalculationForbiddenError(ApplicationError):
    """Пересчёт разрешён только для последнего закрытого периода (7.2)."""

    code = "RECALCULATION_FORBIDDEN"


class ScheduleDayNotEditableError(ApplicationError):
    """День Графика редактируем ⇔ accepts_ut(D) = Да по дню-якорю (16.3)."""

    code = "SCHEDULE_DAY_NOT_EDITABLE"

    def __init__(self, employee_id: str, day: dt.date):
        self.employee_id, self.day = employee_id, day
        super().__init__(f"{employee_id}: schedule day {day} is not editable")


class TimesheetLockedError(ApplicationError):
    """Запись в более ранние закрытые периоды запрещена (16.5, RUL-CLOSED-PERIOD-IMMUTABLE)."""

    code = "TIMESHEET_LOCKED"


class TimesheetOutsideEmploymentError(ApplicationError):
    """День вне интервала трудоустройства: строка Табеля породила бы CHK-DAYS-IN-PERIOD
    (7.1, v7.1/R35 — периоды вне трудоустройства не учитываются)."""

    code = "TIMESHEET_OUTSIDE_EMPLOYMENT"


class SeedNotAllowedError(ApplicationError):
    """Посев OPENING_SEED разрешён только для первого периода сотрудника (v7.1/R37)."""

    code = "SEED_NOT_ALLOWED"


class AdjustmentClosedPeriodError(ApplicationError):
    """Корректировки закрытого периода невозможны — только через recalculate (7.2)."""

    code = "ADJUSTMENT_CLOSED_PERIOD"
