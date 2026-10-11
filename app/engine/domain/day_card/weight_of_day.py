"""weight_of_day(day, st) — вес часа переработки дня: 2 при «Двойные переработки = Да»,
иначе 1 (CFG-MODIFIERS, RUL-CODE-NOTATION)."""
from __future__ import annotations

from ..settings.resolve_modifier import resolve_modifier
from ..settings.types import MOD_DOUBLE, Settings
from ..types.entities import Day


def weight_of_day(day: Day, st: Settings) -> int:
    return 2 if resolve_modifier(MOD_DOUBLE, day, st) else 1
