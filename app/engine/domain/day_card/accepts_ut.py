"""accepts_ut(day, st) — «Принимает коды УТ» из CFG-DAY-CODES (5.2)."""
from __future__ import annotations

from ..settings.types import Settings
from ..types.entities import Day
from .policy_of import policy_of


def accepts_ut(day: Day, st: Settings) -> bool:
    return policy_of(day, st).accepts_ut
