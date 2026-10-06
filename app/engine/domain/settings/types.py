"""Справочники и настройки расчёта (раздел 5)."""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Mapping

Segment = tuple[int, int]          # [start_minute, end_minute) внутри суток

# имена модификаторов Т4 (это имена настроек, а не бизнес-коды Табеля)
MOD_DOUBLE = "double_overtime"         # Двойные переработки: Да/Нет
MOD_PAYS = "pays_overtime"             # Оплачиваются ли переработки: Да/Нет
MOD_PLAN_EQUALS_FACT = "plan_equals_fact"  # План=Факт: Да/Нет/Авто
MOD_COUNTS_IN_UT = "counts_in_ut"      # Учитываются ли часы в УТ: Да/Нет
AUTO = "auto"
MODIFIER_NAMES = (MOD_DOUBLE, MOD_PAYS, MOD_PLAN_EQUALS_FACT, MOD_COUNTS_IN_UT)


@dataclass(frozen=True)
class DayCodePolicy:                    # строка Т1
    code: str
    carries_hours: bool
    accepts_ut: bool
    counts_in_ut: bool
    plan_equals_fact_auto: bool
    activity_requires_review: bool
    title: str = ""


@dataclass(frozen=True)
class Window:                           # строка Т2; ключ — значение Табеля
    code: str
    plan_minutes: int
    segments: tuple[Segment, ...]

    @property
    def length(self) -> int:
        return sum(end - start for start, end in self.segments)


@dataclass(frozen=True)
class Category:                         # строка Т3 + коды УТ по весам
    name: str
    segments: tuple[Segment, ...]
    tariffs: Mapping[int, str]          # вес → код УТ


@dataclass(frozen=True)
class Group:                            # строка Т-Группы
    name: str
    plan_equals_fact_auto: bool
    title: str = ""


@dataclass(frozen=True)
class Modifier:                         # строка Т4 (одно переопределение)
    name: str
    value: object                       # True / False / AUTO
    employee_id: str | None = None
    group: str | None = None
    day: dt.date | None = None          # None — на весь период


@dataclass(frozen=True)
class PlacementPolicy:                  # Т9
    tariff_order: tuple[str, ...]


@dataclass(frozen=True)
class Settings:
    day_codes: Mapping[str, DayCodePolicy]
    windows: Mapping[str, Window]
    categories: tuple[Category, ...]
    weights: Mapping[str, int]          # Т5
    cascade_order: tuple[str, ...]      # Т6 (после банка)
    placement: PlacementPolicy          # Т9
    groups: Mapping[str, Group]
    employee_groups: Mapping[str, str] = field(default_factory=dict)
    modifiers: tuple[Modifier, ...] = ()
    step_minutes: int = 60              # Т7
    late_limit_minutes: int = 5         # Т7
    day_limit_minutes: int = 1440       # Т7
    double_weight: int = 2              # вес часа при «Двойные переработки = Да»
    tz: str = "Europe/Moscow"
    versions: tuple[str, ...] = ()
