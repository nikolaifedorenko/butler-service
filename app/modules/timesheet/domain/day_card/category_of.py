"""category_of(minute, st) — категория минуты (0..1439) с учётом перехода через полночь
(CFG-CATEGORIES: end ≤ start означает [start, 24:00) ∪ [00:00, end))."""
from __future__ import annotations

from ..settings.types import Settings
from ..types.errors import ConfigError


def _covers(minute: int, start: int, end: int) -> bool:
    return start <= minute < end if end > start else minute >= start or minute < end


def category_of(minute: int, st: Settings) -> str:
    for c in st.categories:
        if _covers(minute, c.start_minute, c.end_minute):
            return c.code
    raise ConfigError([("CHK-CATEGORIES-COVER", {"minute": minute})])
