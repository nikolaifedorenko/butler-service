"""resolve_modifier(name, day, st) — разрешение модификатора CFG-MODIFIERS по приоритету
1–7 (CFG-MODIFIERS, 3.5): сотрудник+день … период, глобальный дефолт. Подневно;
сотрудник и группа — из строки дня (RUL-GROUP-PER-DAY). Значение обязано разрешиться;
для «Учитываются ли часы в УТ» уровнем 7 служит колонка CFG-DAY-CODES."""
from __future__ import annotations

from ..types.entities import Day
from ..types.errors import ConfigError
from .checks.modifier_scope import scope_level
from .types import MOD_COUNTS_IN_UT, Settings


def _matches(entry, day: Day) -> bool:
    """Запись матчает день D (область уже каноническая — уровень 1–6)."""
    if entry.employee_id is not None and entry.employee_id != day.employee_id:
        return False
    if entry.group is not None and entry.group != day.group:
        return False
    if entry.day is not None and entry.day != day.day:
        return False
    return entry.period is None or entry.period.start <= day.day <= entry.period.end


def _default_of(name: str, day: Day, st: Settings):
    """Уровень 7: глобальный дефолт; для counts_in_ut — колонка CFG-DAY-CODES."""
    if name == MOD_COUNTS_IN_UT:
        return st.day_code_policy[day.code].counts_in_ut
    value = getattr(st.global_defaults, name, None)
    if value is None:
        raise ConfigError([("CHK-DEFAULTS", {"modifier": name})])
    return value


def resolve_modifier(name: str, day: Day, st: Settings):
    levels = sorted(((scope_level(e), i, e) for i, e in enumerate(st.modifiers)
                     if e.name == name and scope_level(e) is not None))
    for _, _, entry in levels:
        if _matches(entry, day):
            return entry.value
    return _default_of(name, day, st)
