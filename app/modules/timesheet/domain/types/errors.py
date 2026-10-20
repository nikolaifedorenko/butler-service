"""Типизированные исключения домена (2.8). Никаких `-1`, `None`-как-ошибка,
проглатывания исключений; бизнес-ситуации — структурированные записи, не ошибки."""
from __future__ import annotations

import datetime as dt
from typing import Mapping, Sequence


class DomainError(Exception):
    """База для всех ошибок домена."""


class ConfigError(DomainError):
    """Противоречивая или неполная конфигурация (5.3, уровень 1); отсутствие строки
    в справочнике; некорректные данные Графика (уровень 3 — бросает адаптер)."""

    def __init__(self, violations: Sequence[tuple[str, Mapping[str, object]]]):
        self.violations = tuple((code, dict(data)) for code, data in violations)
        super().__init__("; ".join(f"{code}: {data}" for code, data in self.violations))


class UnknownDayCodeError(DomainError):
    """Код дня Табеля отсутствует в CFG-DAY-CODES (CHK-DAY-CODE-KNOWN)."""

    def __init__(self, code: str, day: dt.date):
        self.code, self.day = code, day
        super().__init__(f"CHK-DAY-CODE-KNOWN: {code!r} on {day}")


class UnknownTimesheetValueError(DomainError):
    """Значение Табеля, несущее часы, не имеет строки в CFG-WINDOWS (CHK-WINDOW-EXISTS)."""

    def __init__(self, value: str):
        self.value = value
        super().__init__(f"CHK-WINDOW-EXISTS: {value!r}")


class InvalidInputDataError(DomainError):
    """Нарушение правил входных данных (3.3, 5.3, уровень 2). Код совпадает с именем проверки."""

    def __init__(self, code: str, data: Mapping[str, object] | None = None):
        self.code, self.data = code, dict(data or {})
        super().__init__(f"{code}: {self.data}")


class IncompleteTimesheetError(DomainError):
    """Табель не покрывает период: пропущен день либо день продублирован
    (RUL-TIMESHEET-COVERS-PERIOD, CHK-TIMESHEET-COVERS)."""

    def __init__(self, missing: Sequence[dt.date] = (), duplicated: Sequence[dt.date] = ()):
        self.missing, self.duplicated = tuple(missing), tuple(duplicated)
        super().__init__(f"CHK-TIMESHEET-COVERS: missing={list(self.missing)} duplicated={list(self.duplicated)}")


class IncompletePeriodError(DomainError):
    """`close` запрошен раньше 00:00 дня, следующего за period.end, по исходному `now`
    (CHK-CLOSE-ALLOWED)."""

    def __init__(self, period_end: dt.date, now: dt.datetime):
        self.period_end, self.now = period_end, now
        super().__init__(f"CHK-CLOSE-ALLOWED: period ending {period_end} at {now}")


class InvariantViolationError(DomainError):
    """Нарушен инвариант (10): ошибка реализации, расчёт прерывается, результат не сохраняется."""

    def __init__(self, code: str, data: Mapping[str, object] | None = None):
        self.code, self.data = code, dict(data or {})
        super().__init__(f"{code}: {self.data}")
