"""receiver_ok(day, st) — допустимый приёмник переноса (5.2): accepts_ut И pays_overtime."""
from __future__ import annotations

from ..settings.types import Settings
from ..types.entities import Day
from .accepts_ut import accepts_ut
from .pays_overtime import pays_overtime


def receiver_ok(day: Day, st: Settings) -> bool:
    return accepts_ut(day, st) and pays_overtime(day, st)
