"""CHK-CATEGORIES-COVER: категории покрывают сутки без дыр и перекрытий с учётом
перехода через полночь (end ≤ start — интервал [start, 24:00) ∪ [00:00, end))."""
from __future__ import annotations

from ..types import Category, Settings
from ._violations import Violation

CHK_CATEGORIES_COVER = "CHK-CATEGORIES-COVER"


def _covers(minute: int, c: Category) -> bool:
    return c.start_minute <= minute < c.end_minute if c.end_minute > c.start_minute \
        else minute >= c.start_minute or minute < c.end_minute


def check_categories_cover(st: Settings) -> list[Violation]:
    counts = [sum(1 for c in st.categories if _covers(m, c)) for m in range(1440)]
    holes = tuple(m for m, n in enumerate(counts) if n == 0)
    overlaps = tuple(m for m, n in enumerate(counts) if n > 1)
    if not holes and not overlaps:
        return []
    return [(CHK_CATEGORIES_COVER, {"holes": holes[:8], "overlaps": overlaps[:8]})]
