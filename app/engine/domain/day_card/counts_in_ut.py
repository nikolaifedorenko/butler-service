"""counts_in_ut(day, st) — «Учитываются ли часы в УТ» (5.2): модификатор по приоритету,
уровень 7 — колонка CFG-DAY-CODES."""
from __future__ import annotations

from ..settings.resolve_modifier import resolve_modifier
from ..settings.types import MOD_COUNTS_IN_UT, Settings
from ..types.entities import Day


def counts_in_ut(day: Day, st: Settings) -> bool:
    return bool(resolve_modifier(MOD_COUNTS_IN_UT, day, st))
