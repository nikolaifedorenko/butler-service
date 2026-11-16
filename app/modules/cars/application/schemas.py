"""Модели данных раздела «Электрокары», которые отдаёт прикладной слой — в том числе другим
модулям (обход каров в ночном отчёте)."""
from __future__ import annotations

from typing import Optional

from app.core.schemas import ApiModel, PhotoOut


class CarOut(ApiModel):
    id: int
    number: str
    status: str
    status_title: str
    location: str
    charge: str
    charge_title: str
    on_charge: bool
    canopy: bool
    condition: str
    trash: bool
    clean: bool
    has_key: bool
    holder_user_id: Optional[int]
    holder_name: str
    assigned_to: Optional[int]
    assigned_name: str
    note: str
    last_checked_at: Optional[str]      # местное время объекта
    last_taken_at: Optional[str]
    active: bool


class NightCarCheckOut(ApiModel):
    """Отметка кара в ночном обходе."""

    id: int
    found: bool
    location: str               # где кар оставлен
    found_location: str         # где кар найден
    moved: bool                 # кар переставлен
    canopy: bool
    charge: str
    on_charge: bool
    condition: str
    trash: bool
    clean: bool
    comment: str
    checker_name: str
    checked_at: Optional[str]
    taken_after_check: bool     # кар взяли уже после проверки
    photos: list[PhotoOut]


class NightCarEntryOut(ApiModel):
    car: CarOut
    checked: bool
    check: Optional[NightCarCheckOut]


class NightCarsStateOut(ApiModel):
    """Шаг «Проверка электрокаров» за смену."""

    report_id: int
    cars_step_done: bool
    total: int
    checked: int
    unchecked: int
    problems: int               # не найден или техсостояние «не ОК»
    list: list[NightCarEntryOut]


class NightCarCheckSavedOut(ApiModel):
    id: int
    found: bool
    checked_at: Optional[str]
