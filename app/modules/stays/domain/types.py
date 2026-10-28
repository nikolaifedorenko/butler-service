"""Общие типы домена покрытия (§3.4, §4.2–§4.5)."""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Mapping


@dataclass(frozen=True)
class DutyDay:
    """День батлера по Графику: смена, код дня Табеля, отлучка внутри смены."""
    on_shift: bool
    code: str | None              # код дня Табеля (ОТ, Б, В…)
    partial_absence: bool


OFF = DutyDay(False, None, False)


@dataclass(frozen=True)
class StayDay:
    """Одна бронь в один день: где ночуют её гости (объект — по сегменту на PM даты)."""
    day: dt.date
    reservation_id: int
    group_id: int | None
    unit_id: int | None
    group_path: tuple[int, ...]                # узел объекта в дереве фонда дня, от корня
    weight: float
    escorted: bool
    declined: bool
    guests: Mapping[int, str]                  # guest_id → уровень (regular | vip | vvip)


@dataclass(frozen=True)
class Line:
    """Строка покрытия: батлер на день ведёт бронь, группу или выбранных гостей."""
    id: int
    day: dt.date
    employee_id: int
    reservation_id: int | None
    group_id: int | None
    guest_ids: frozenset[int]                  # пусто — вся бронь или вся группа
    source: str
    overnight: bool


@dataclass(frozen=True)
class DayCover:
    by_guest: dict[tuple[int, int], tuple[int, ...]]      # (бронь, гость) → батлеры
    uncovered: dict[int, tuple[int, ...]]                 # бронь → гости без батлера
    double: list[tuple[int, int, tuple[int, ...]]] = field(default_factory=list)


@dataclass(frozen=True)
class Warning:
    kind: str           # hole | need_replacement | off_shift | overload | double_cover
    day: dt.date
    employee_id: int | None
    reservation_id: int | None
    unit_id: int | None
    value: str = ""     # код дня, нагрузка «10/8», гость — для текста в прикладном слое


@dataclass(frozen=True)
class Candidate:
    employee_id: int
    knows_guest: bool
    same_place: bool
    load_after: float
    note: str = ""
