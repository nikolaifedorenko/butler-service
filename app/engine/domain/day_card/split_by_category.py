"""split_by_category(interval, st) — суммы минут интервала по категориям (RUL-OVERTIME-CATEGORIES)."""
from __future__ import annotations

from ..settings.types import Settings
from ..types.entities import Interval, Minutes
from .category_cuts import category_cuts


def split_by_category(interval: Interval, st: Settings) -> tuple[tuple[str, Minutes], ...]:
    totals: dict[str, Minutes] = {}
    for code, piece in category_cuts(interval, st):
        totals[code] = totals.get(code, 0) + piece.length
    return tuple(totals.items())
