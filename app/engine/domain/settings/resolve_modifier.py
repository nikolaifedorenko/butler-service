from __future__ import annotations

import datetime as dt

from .types import Modifier, Settings


def _rank(m: Modifier, employee_id: str, group: str, day: dt.date) -> int | None:
    """Приоритет Т4: 1 — сотрудник+день … 6 — все+период; None — строка не подходит."""
    if m.day is not None and m.day != day:
        return None
    level = 0 if m.employee_id is not None else (2 if m.group is not None else 4)
    if (m.employee_id, m.group) != (employee_id if level == 0 else None, group if level == 2 else None):
        return None
    return level + (1 if m.day is not None else 2)


def resolve_modifier(name: str, employee_id: str, group: str, day: dt.date, st: Settings,
                     default: object) -> object:
    """Значение модификатора Т4 по приоритету (5, Т4); default — значение из Т1–Т2."""
    ranked = [(r, i, m.value) for i, m in enumerate(st.modifiers) if m.name == name
              for r in [_rank(m, employee_id, group, day)] if r is not None]
    return min(ranked)[2] if ranked else default
