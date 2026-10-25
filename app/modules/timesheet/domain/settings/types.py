"""Структура Settings и справочников (3.5). `Settings` — неизменяемый разрешённый
набор конфигурации на период; единственный источник tz, шага и лимитов (2.6)."""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Final, Literal, Mapping, Sequence
from zoneinfo import ZoneInfo

from ..types.entities import MinuteOfDay, Minutes, Period, StepMinutes
from ..types.immutable import freeze_mapping

# имена модификаторов CFG-MODIFIERS (имена настроек, не бизнес-коды Табеля)
MOD_DOUBLE = "double_overtime"            # Двойные переработки: Да/Нет
MOD_PAYS = "pays_overtime"                # Оплачиваются ли переработки: Да/Нет
MOD_PLAN_EQUALS_FACT = "plan_equals_fact"  # План=Факт: Да/Нет/Авто
MOD_COUNTS_IN_UT = "counts_in_ut"         # Учитываются ли часы в УТ: Да/Нет
MODIFIER_NAMES = (MOD_DOUBLE, MOD_PAYS, MOD_PLAN_EQUALS_FACT, MOD_COUNTS_IN_UT)

# значения модификатора «План=Факт» (CHK-MODIFIER-TYPE)
PEF_YES = "yes"
PEF_NO = "no"
PEF_AUTO = "auto"
PEF_VALUES = (PEF_YES, PEF_NO, PEF_AUTO)

# гранулярность периода (3.5, v7.1/R36)
GRANULARITY_MONTH: Final = "month"
GRANULARITY_HALF_MONTH: Final = "half_month"


@dataclass(frozen=True)
class DayCodePolicy:
    """Строка CFG-DAY-CODES (3.5)."""

    carries_hours: bool               # несёт плановые часы
    accepts_ut: bool                  # принимает коды УТ
    counts_in_ut: bool                # дефолт модификатора «Учитываются ли часы в УТ» (уровень 7)
    plan_equals_fact_auto: bool       # «План=Факт = Авто» разрешается в «Да» (единственный источник «Авто», v7)


@dataclass(frozen=True)
class Window:
    """Строка CFG-WINDOWS (3.5): только границы окна; плана в строке нет (v7.1/R34)."""

    start_minute: MinuteOfDay         # 0..1440
    end_minute: MinuteOfDay           # 0..1440, > start_minute (окно не пересекает полночь)

    @property
    def length(self) -> Minutes:
        return self.end_minute - self.start_minute


@dataclass(frozen=True)
class Category:
    """Строка CFG-CATEGORIES (3.5). end <= start — категория пересекает полночь."""

    code: str                         # база кода УТ: «ДЯ» | «ДН»
    start_minute: MinuteOfDay
    end_minute: MinuteOfDay


@dataclass(frozen=True)
class Group:
    """Запись реестра CFG-GROUPS (v7: без полей — «Авто» разрешается только колонкой
    CFG-DAY-CODES, R19)."""


@dataclass(frozen=True)
class ModifierEntry:
    """Запись CFG-MODIFIERS (3.5). Допустимы ровно шесть форм области действия
    (CHK-MODIFIER-SCOPE): (employee, day) | (employee, period) | (group, day)
    | (group, period) | (day) | (period)."""

    name: Literal["double_overtime", "pays_overtime", "plan_equals_fact", "counts_in_ut"]
    value: bool | str                 # bool для всех, кроме plan_equals_fact: "yes"|"no"|"auto"
    employee_id: str | None = None    # None — все сотрудники
    group: str | None = None          # None — любая группа
    day: dt.date | None = None        # None — без привязки к дню
    period: Period | None = None      # None — без привязки к периоду


@dataclass(frozen=True)
class GlobalDefaults:
    """Глобальные подстраховки CFG-MODIFIERS, уровень 7 (3.5, CHK-DEFAULTS).
    None — обязательная строка отсутствует (конфигурация невалидна)."""

    double_overtime: bool | None = None
    pays_overtime: bool | None = None
    plan_equals_fact: str | None = None


@dataclass(frozen=True)
class Settings:
    """Неизменяемый разрешённый набор конфигурации на период (3.5)."""

    tz: ZoneInfo = field(default_factory=lambda: ZoneInfo("Europe/Moscow"))
    period_granularity: Literal["month", "half_month"] = GRANULARITY_MONTH
    step_minutes: StepMinutes = 60                                    # CFG-LIMITS
    late_limit_minutes: Minutes = 5                                   # CFG-LIMITS
    day_limit_minutes: Minutes = 1440                                 # CFG-LIMITS
    day_code_policy: Mapping[str, DayCodePolicy] = field(default_factory=dict)   # CFG-DAY-CODES
    windows: Mapping[str, Window] = field(default_factory=dict)                  # CFG-WINDOWS
    categories: tuple[Category, ...] = ()                                        # CFG-CATEGORIES
    weights: Mapping[str, int] = field(default_factory=dict)                     # CFG-WEIGHTS
    cascade_order: tuple[str, ...] = ()                                          # CFG-CASCADE
    placement_order: tuple[str, ...] = ()                                        # CFG-PLACEMENT
    groups: Mapping[str, Group] = field(default_factory=dict)                    # CFG-GROUPS
    modifiers: Sequence[ModifierEntry] = ()                                      # CFG-MODIFIERS
    global_defaults: GlobalDefaults = field(default_factory=GlobalDefaults)
    versions: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        # глубокая неизменяемость (2.5): read-only представления по копиям
        object.__setattr__(self, "day_code_policy", freeze_mapping(self.day_code_policy))
        object.__setattr__(self, "windows", freeze_mapping(self.windows))
        object.__setattr__(self, "weights", freeze_mapping(self.weights))
        object.__setattr__(self, "groups", freeze_mapping(self.groups))
        object.__setattr__(self, "categories", tuple(self.categories))
        object.__setattr__(self, "cascade_order", tuple(self.cascade_order))
        object.__setattr__(self, "placement_order", tuple(self.placement_order))
        object.__setattr__(self, "modifiers", tuple(self.modifiers))
        object.__setattr__(self, "versions", tuple(self.versions))
