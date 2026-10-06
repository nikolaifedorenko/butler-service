from __future__ import annotations

from dataclasses import dataclass

from ..domain.types.results import FlagsResult, SettleResult


@dataclass(frozen=True)
class PeriodView:
    """Склейка SettleResult и FlagsResult (представление дня = карточка + её флаги)."""
    settle: SettleResult
    flags: FlagsResult
    settings_versions: tuple[str, ...] = ()
    closed: bool = False

    def flags_of(self, day):
        return tuple(f for f in self.flags.flags if f.day == day)
