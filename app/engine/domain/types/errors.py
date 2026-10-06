"""Типизированные исключения домена (2.8)."""
from __future__ import annotations

from typing import Mapping, Sequence


class DomainError(Exception):
    """База для всех ошибок домена."""


class ConfigError(DomainError):
    def __init__(self, violations: Sequence[tuple[str, Mapping[str, object]]]):
        self.violations = tuple(violations)
        super().__init__("; ".join(f"{code}: {dict(data)}" for code, data in self.violations))


class UnknownDayCodeError(DomainError):
    def __init__(self, code: str, day):
        self.code, self.day = code, day
        super().__init__(f"unknown day code {code!r} on {day}")


class IncompletePeriodError(DomainError):
    def __init__(self, period_end, now):
        self.period_end, self.now = period_end, now
        super().__init__(f"period ending {period_end} is not complete at {now}")


class InvariantViolationError(DomainError):
    def __init__(self, code: str, data: Mapping[str, object]):
        self.code, self.data = code, dict(data)
        super().__init__(f"{code}: {self.data}")
