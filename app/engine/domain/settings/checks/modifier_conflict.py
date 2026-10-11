"""CHK-MODIFIER-CONFLICT: нет двух записей одного уровня одного модификатора, матчащих
один день, независимо от равенства значений (3.5, 5.3)."""
from __future__ import annotations

from ..types import Settings
from ._violations import Violation
from .modifier_scope import scope_level

CHK_MODIFIER_CONFLICT = "CHK-MODIFIER-CONFLICT"


def _same_scope(a, b) -> bool:
    """Записи одного уровня матчают один и тот же день."""
    if a.employee_id != b.employee_id or a.group != b.group or a.day != b.day:
        return False
    if a.day is not None:
        return True
    return _periods_intersect(a, b)


def _periods_intersect(a, b) -> bool:
    if a.period is None or b.period is None:
        return a.period is None and b.period is None
    return max(a.period.start, b.period.start) <= min(a.period.end, b.period.end)


def check_modifier_conflict(st: Settings) -> list[Violation]:
    entries = [(i, e, scope_level(e)) for i, e in enumerate(st.modifiers)]
    out = []
    for ai, (i, a, la) in enumerate(entries):
        for j, b, lb in entries[ai + 1:]:
            if la is not None and la == lb and a.name == b.name and _same_scope(a, b):
                out.append((CHK_MODIFIER_CONFLICT, {"name": a.name, "level": la, "entries": (i, j)}))
    return out
