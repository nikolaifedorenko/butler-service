"""Модели запросов и ответов раздела «Электрокары»."""
from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel

from app.core.schemas import ApiModel, PhotoOut

from ..application.schemas import CarOut

# ── запросы ──────────────────────────────────────────────────────────────────


class TakeIn(BaseModel):
    ack_assigned: bool = False


class HandoverIn(BaseModel):
    employee_id: Optional[int] = None
    name: str = ""
    with_key: bool = True
    comment: str = ""


class GiveIn(BaseModel):
    employee_id: Optional[int] = None
    name: str = ""
    with_key: bool = True


class AssignIn(BaseModel):
    employee_id: Optional[int] = None      # пусто / 0 — снять закрепление


class StatusIn(BaseModel):
    status: str
    note: str = ""


class CarIn(BaseModel):
    number: str
    location: str = ""


class CarEditIn(BaseModel):
    number: Optional[str] = None
    location: Optional[str] = None
    note: Optional[str] = None
    active: Optional[bool] = None


class LocationIn(BaseModel):
    name: str


class LocationEditIn(BaseModel):
    name: Optional[str] = None
    active: Optional[bool] = None


# ── ответы ───────────────────────────────────────────────────────────────────


class CodeTitle(ApiModel):
    code: str
    title: str


class MetaOut(ApiModel):
    """Словари раздела и права пользователя."""

    statuses: list[CodeTitle]
    actions: list[CodeTitle]
    charges: list[CodeTitle]
    can_use: bool
    can_issue: bool
    can_manage: bool
    can_edit_park: bool


class LocationOut(ApiModel):
    id: int
    name: str
    sort_order: int
    active: bool
    builtin: bool


class LocationsOut(ApiModel):
    locations: list[LocationOut]


class LocationAddedOut(ApiModel):
    id: int
    name: str
    restored: bool          # место уже было в справочнике и включено заново


class MyCarsOut(ApiModel):
    """Кары текущего сотрудника: какой держит, какой закреплён, какой свободный предложить."""

    held: Optional[int]
    free_recommended: Optional[int]
    assigned: Optional[int]


class ParkOut(ApiModel):
    cars: list[CarOut]
    me: Optional[MyCarsOut]             # нет у учётной записи без сотрудника
    can_manage: bool


class CarOperationOut(ApiModel):
    ok: bool = True
    car: CarOut


class HistoryItemOut(ApiModel):
    id: int
    ts: Optional[str]
    action: str
    action_title: str
    actor_name: str
    person: str
    with_key: Optional[bool]
    location: str
    details: dict[str, Any]
    photos: list[PhotoOut]


class HistoryOut(ApiModel):
    history: list[HistoryItemOut]
