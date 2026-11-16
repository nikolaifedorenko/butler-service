"""Модели запросов и ответов раздела «Сотрудники»."""
from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel

from app.core.schemas import ApiModel

# ── запросы ──────────────────────────────────────────────────────────────────


class SuggestGenitiveIn(BaseModel):
    full_name: str


class DatedAction(BaseModel):
    """Перевод, смена блока графика или увольнение с даты (пусто — с сегодняшней)."""

    date: Optional[str] = None
    position: str = ""
    group: str = ""
    # свой шаблон блока: у пятидневки — свои выходные, у «Других смен» — свой цикл
    kind: str = ""                 # base | week5 | cycle | manual (пусто — по типу блока)
    value: str = ""                # значение рабочего дня («Я 10,75»)
    cycle: str = ""                # "3/3", "1/3", "custom:РРВВРВ"
    anchor: Optional[str] = None   # опорная дата цикла
    off_weekdays: list[int] = []   # выходные дни недели (0 — пн … 6 — вс) для пятидневки
    label: str = ""


class RehireIn(DatedAction):
    """Повторный приём: date — первый рабочий день."""


# ── ответы ───────────────────────────────────────────────────────────────────


class ContactOut(ApiModel):
    id: int
    name: str
    phone: str
    relation: str


class EmployeeOut(ApiModel):
    id: int
    full_name: str
    short_name: str
    full_name_genitive: str
    full_name_genitive_hint: str    # родительный падеж: заданный либо предложенный
    position: str
    phone: str
    tab_number: str
    hired_at: Optional[str]
    emergency_name: str
    emergency_phone: str
    telegram: str
    email: str
    dismissed_at: Optional[str]
    contacts: list[ContactOut]
    department_id: Optional[int]
    department: Optional[str]
    nationality: str
    subdivision: str
    schedule_group: str
    group_color: str
    schedule_pattern: str
    active: bool
    deleted: bool                   # скрыт из списков; история сохранена
    deleted_at: Optional[str]
    assigned_car_id: Optional[int]
    assigned_car_number: str


class EmployeeUserOut(EmployeeOut):
    """Сотрудник с учётной записью."""

    username: Optional[str]
    role: Optional[str]


class EmployeeCreatedOut(EmployeeUserOut):
    initial_password: Optional[str]     # сгенерированный пароль; показывается один раз


class GenitiveOut(ApiModel):
    genitive: str


class PositionPeriodOut(ApiModel):
    position: str
    start: str
    end: Optional[str]


class EmploymentPeriodOut(ApiModel):
    start: str
    end: Optional[str]
    note: str
    current: bool


class EmployeeHistoryOut(ApiModel):
    positions: list[PositionPeriodOut]
    blocks: list[dict[str, Any]]            # периоды в блоках графика — данные табеля
    current_value: Any
    employment: list[EmploymentPeriodOut]
    bank_adjustments: list[dict[str, Any]]
    bank_now: Any


class NamedOut(ApiModel):
    id: int
    name: str


class SubdivisionRenamedOut(NamedOut):
    employees_updated: int


class DepartmentDeletedOut(ApiModel):
    ok: bool = True
    unlinked_employees: int


class SubdivisionDeletedOut(ApiModel):
    ok: bool = True
    employees_cleared: int
