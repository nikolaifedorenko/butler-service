"""classify_overtime(parts, st) — суммы переработки по категориям (6.3, стадия 5)."""
from __future__ import annotations

from typing import Mapping, Sequence

from ..settings.types import Settings
from ..types.entities import Interval, Minutes
from .split_by_category import split_by_category


def classify_overtime(parts: Sequence[Interval], st: Settings) -> Mapping[str, Minutes]:
    totals: dict[str, Minutes] = {}
    for part in parts:
        for code, minutes in split_by_category(part, st):
            totals[code] = totals.get(code, 0) + minutes
    return totals
