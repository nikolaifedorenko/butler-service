from ..settings.types import Settings
from ..types.entities import Interval


def category_cuts(interval: Interval, st: Settings) -> tuple[int, ...]:
    """Точки разреза интервала границами категорий Т3 (включая концы интервала)."""
    inner = {b for c in st.categories for s in c.segments for b in s
             if interval.start_minute < b < interval.end_minute}
    return tuple(sorted(inner | {interval.start_minute, interval.end_minute}))
