"""pays_overtime(day, st) — оплачиваемость дня (5.2, единственное нормативное место):
counts_in_ut(D) И «Оплачиваются ли переработки»(D)."""
from __future__ import annotations

from ..settings.resolve_modifier import resolve_modifier
from ..settings.types import MOD_PAYS, Settings
from ..types.entities import Day
from .counts_in_ut import counts_in_ut


def pays_overtime(day: Day, st: Settings) -> bool:
    return counts_in_ut(day, st) and bool(resolve_modifier(MOD_PAYS, day, st))
