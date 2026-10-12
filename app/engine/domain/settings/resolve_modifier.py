"""resolve_modifier(name, day, st) — разрешение модификатора CFG-MODIFIERS по приоритету
1–7 (CFG-MODIFIERS, 3.5): сотрудник+день … период, глобальный дефолт. Подневно;
сотрудник и группа — из строки дня (RUL-GROUP-PER-DAY). Значение обязано разрешиться;
для «Учитываются ли часы в УТ» уровнем 7 служит колонка CFG-DAY-CODES.

`resolve_modifier_trace` возвращает ТО ЖЕ значение плюс объяснение (уровень и
выигравшую запись) — его использует «Проверитель» в настройках: менеджер видит,
какое правило подействовало и почему, без чтения трассы расчёта. Приоритет
реализован один раз, здесь; интерфейсный слой объяснение только оформляет.
"""
from __future__ import annotations

from dataclasses import dataclass

from ..types.entities import Day
from ..types.errors import ConfigError
from .checks.modifier_scope import scope_level
from .types import MOD_COUNTS_IN_UT, ModifierEntry, Settings


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


@dataclass(frozen=True)
class ModifierResolution:
    """Значение модификатора для дня + уровень приоритета, на котором оно взято.

    level 1–6 — запись CFG-MODIFIERS (`entry`), level 7 — глобальный дефолт версии
    либо колонка кода Табеля (`entry is None`).
    """

    value: bool | str
    level: int
    entry: ModifierEntry | None


def resolve_modifier_trace(name: str, day: Day, st: Settings) -> ModifierResolution:
    levels = sorted(((scope_level(e), i, e) for i, e in enumerate(st.modifiers)
                     if e.name == name and scope_level(e) is not None))
    for level, _, entry in levels:
        if _matches(entry, day):
            return ModifierResolution(entry.value, level, entry)
    return ModifierResolution(_default_of(name, day, st), 7, None)


def resolve_modifier(name: str, day: Day, st: Settings):
    return resolve_modifier_trace(name, day, st).value
