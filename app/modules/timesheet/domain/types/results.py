"""Результаты расчётов и представления (3.2, 16.2, 16.4). Глубокая неизменяемость — 2.5."""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Mapping

from .entities import DeferredBlock, Minutes, Session
from .immutable import freeze_data, freeze_mapping_of_minutes, freeze_nested_mapping


@dataclass(frozen=True)
class Reason:
    """Запись трассы/исключения: шаг (каноническое перечисление 6.2), код, исчерпывающие data."""

    step: str
    code: str
    data: Mapping[str, object]

    def __post_init__(self) -> None:
        object.__setattr__(self, "data", freeze_data(self.data))


@dataclass(frozen=True)
class Flag:
    """Информационный флаг дня: код из реестра 6.6 + параметры (DataValue)."""

    day: dt.date
    code: str
    data: Mapping[str, object]

    def __post_init__(self) -> None:
        object.__setattr__(self, "data", freeze_data(self.data))


@dataclass(frozen=True)
class Cut:
    """Изъятие кода каскадом (2.7): физические минуты кратны шагу."""

    source_day: dt.date
    placed_day: dt.date | None
    tariff: str
    taken_minutes: Minutes
    paid_minutes: Minutes


@dataclass(frozen=True)
class DayCard:
    """Карточка дня (3.2). plan_minutes = длина окна (v7.1/R34); 0 — без окна и при «План=Факт»."""

    day: dt.date
    timesheet_value: str
    plan_minutes: Minutes
    full_fact_minutes: Minutes
    work_minutes: Minutes
    overtime_minutes: Minutes
    debt_minutes: Minutes
    codes: Mapping[str, Minutes]        # собственные коды дня до снятия/переноса
    pays_overtime: bool
    plan_equals_fact_applied: bool

    def __post_init__(self) -> None:
        object.__setattr__(self, "codes", freeze_mapping_of_minutes(self.codes))


@dataclass(frozen=True)
class SettleResult:
    """Полный результат расчёта часов (3.2). Каноническая форма — 3.4."""

    cards: tuple[DayCard, ...]
    mgmt_timesheet: Mapping[dt.date, Mapping[str, Minutes]]
    bank_open_minutes: Minutes
    bank_open_normalized_minutes: Minutes
    bank_adjustments_minutes: Minutes
    bank_closed_minutes: Minutes
    credited_to_bank_minutes: Minutes
    paid_with_bank_minutes: Minutes
    total_debt_minutes: Minutes
    residual_debt_minutes: Minutes
    cuts: tuple[Cut, ...]
    deferred_blocks: tuple[DeferredBlock, ...]
    exceptions: tuple[Reason, ...]
    trace: tuple[Reason, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "mgmt_timesheet", freeze_nested_mapping(self.mgmt_timesheet))


@dataclass(frozen=True)
class FlagsResult:
    """Снимок флагов периода (3.2)."""

    flags: tuple[Flag, ...] = field(default=())


@dataclass(frozen=True)
class DayView:
    """Представление дня — склейка application (3.2, v7.1/R39):
    карточка + флаги + информационный план строки Табеля."""

    card: DayCard
    flags: tuple[Flag, ...]
    timesheet_plan_minutes: Minutes


@dataclass(frozen=True)
class SessionView:
    """Сессия + признаки диапазона — вкладка «Факт» (3.2, 16.4)."""

    employee_id: str
    session: Session                      # исходные моменты, без округления
    started_before_range: bool = False
    closed_after_range: bool = False


@dataclass(frozen=True)
class EmployeeCard:
    """Карточка открытой сессии — вкладка «Отметки» (3.2, 16.2)."""

    employee_id: str
    open_since_utc: dt.datetime         # исходный момент «пришёл»
    minutes_open: Minutes               # ⌊(now − open_since) / 60с⌋
    expected_today: bool                # ожидаемые подинтервалы сегодня непусты
    shift_today: tuple[tuple[dt.datetime, dt.datetime], ...]  # дневные отрезки смены (без вычета отсутствий)


@dataclass(frozen=True)
class ExpectedArrival:
    """«Кто ещё должен прийти» (3.2, 16.2, v7.1/R40 — одна ближайшая запись на сотрудника)."""

    employee_id: str
    expected_at_utc: dt.datetime        # начало ближайшего незавершённого ожидаемого подинтервала
    already_started: bool               # True — должен был прийти, но отсутствует


@dataclass(frozen=True)
class PresenceBoard:
    """Доска «прямо сейчас» (3.2, 16.2)."""

    at_work_now: int                                # (a)
    expected_now: int                               # (b)
    open_session_cards: tuple[EmployeeCard, ...]    # (c) по возрастанию open_since
    yet_to_come: tuple[ExpectedArrival, ...]        # (d) по возрастанию expected_at
