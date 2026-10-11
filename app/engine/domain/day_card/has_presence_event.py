"""has_presence_event(day, raw_marks, st) — событие присутствия (4.2): в дне есть
исходная отметка с моментом в полуинтервале [00:00, 24:00). Только исходные отметки,
не сессии: сессия, схлопнувшаяся округлением в ноль, всё равно даёт событие (EX-48)."""
from __future__ import annotations

from ..settings.types import Settings
from ..time.local_midnight import local_midnight, next_midnight
from ..types.entities import Day


def has_presence_event(day: Day, raw_marks, st: Settings) -> bool:
    lo, hi = local_midnight(day.day, st.tz), next_midnight(day.day, st.tz)
    return any(lo <= m.at_utc < hi for m in raw_marks)
