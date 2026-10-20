"""CHK-MODIFIER-SCOPE: область действия ModifierEntry — ровно одна из шести допустимых
форм (3.5, уровни 1–6 CFG-MODIFIERS); указанная группа существует в CFG-GROUPS."""
from __future__ import annotations

from ..types import ModifierEntry, Settings
from ._violations import Violation

CHK_MODIFIER_SCOPE = "CHK-MODIFIER-SCOPE"


def scope_level(entry: ModifierEntry) -> int | None:
    """Номер уровня приоритета (1–6) либо None — форма области недопустима."""
    emp, group, day, period = entry.employee_id, entry.group, entry.day, entry.period
    if emp and not group and day and not period:
        return 1
    if emp and not group and not day and period:
        return 2
    if not emp and group and day and not period:
        return 3
    if not emp and group and not day and period:
        return 4
    if not emp and not group and day and not period:
        return 5
    if not emp and not group and not day and period:
        return 6
    return None


def check_modifier_scope(st: Settings) -> list[Violation]:
    out = [(CHK_MODIFIER_SCOPE, {"entry": _brief(e), "reason": "invalid_scope_form"})
           for e in st.modifiers if scope_level(e) is None]
    out += [(CHK_MODIFIER_SCOPE, {"entry": _brief(e), "reason": "unknown_group"})
            for e in st.modifiers if e.group is not None and e.group not in st.groups]
    return out


def _brief(entry: ModifierEntry) -> dict:
    return {"name": entry.name, "value": entry.value, "employee_id": entry.employee_id,
            "group": entry.group, "day": entry.day, "period_start": None if entry.period is None
            else entry.period.start, "period_end": None if entry.period is None else entry.period.end}
