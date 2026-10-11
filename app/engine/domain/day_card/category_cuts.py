"""category_cuts(interval, st) — разбиение интервала на куски по границам категорий
(CFG-CATEGORIES): tuple[(код категории, Interval)]. Длительности не округляются (4.5)."""
from __future__ import annotations

from ..settings.types import Settings
from ..types.entities import Interval
from .category_of import category_of


def _bounds(interval: Interval, st: Settings) -> tuple[int, ...]:
    inner = {b for c in st.categories for b in (c.start_minute, c.end_minute)
             if interval.start_minute < b < interval.end_minute}
    return tuple(sorted({interval.start_minute, interval.end_minute} | inner))


def category_cuts(interval: Interval, st: Settings) -> tuple[tuple[str, Interval], ...]:
    points = _bounds(interval, st)
    pairs = zip(points, points[1:], strict=False)
    return tuple((category_of(a, st), Interval(interval.day, a, b)) for a, b in pairs if b > a)
