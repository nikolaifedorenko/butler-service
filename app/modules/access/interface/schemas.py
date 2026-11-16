"""Модели запросов и ответов входа и экрана «Права доступа»."""
from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel

from app.core.schemas import ApiModel

# ── вход: запросы ────────────────────────────────────────────────────────────


class LoginIn(BaseModel):
    username: str
    password: str


class ChangePasswordIn(BaseModel):
    old_password: str
    new_password: str


class ImpersonateIn(BaseModel):
    employee_id: int


# ── вход: ответы ─────────────────────────────────────────────────────────────


class UserOut(ApiModel):
    """Вошедший пользователь; при входе «как сотрудник» — сотрудник, глазами которого смотрят."""

    id: int
    username: str
    role: str
    name: str
    employee_id: Optional[int]
    impersonated: bool


class SessionOut(ApiModel):
    ok: bool = True
    user: UserOut


class RoleTitleOut(ApiModel):
    code: str
    title: str


class TodayPlanOut(ApiModel):
    """План сотрудника на сегодня."""

    date: str
    shift: Optional[dict[str, Any]]     # отрезок Графика; нет — выходной
    planned_start: Optional[str]
    planned_end: Optional[str]
    expected: list[list[str]]           # отрезки «с — по», в которые ждут на работе


class MeOut(ApiModel):
    user: UserOut
    today: Optional[TodayPlanOut]       # нет у учётной записи без сотрудника
    permissions: list[str]
    roles: list[RoleTitleOut]
    assignable_roles: list[str]         # роли, которые пользователь может назначать
    menu: list[dict[str, Any]]          # пункты меню по правам — из манифестов модулей
    settings_screens: list[dict[str, Any]]


# ── права: ответы ────────────────────────────────────────────────────────────


class RoleOut(ApiModel):
    role: str
    title: str
    rank: int                           # уровень роли в иерархии
    max_assignable_rank: int            # до какого уровня её обладатель управляет учётными записями
    builtin: bool
    users: int
    defaults: list[str]                 # права встроенной роли по умолчанию
    overrides: dict[str, str]           # право → allow | deny
    effective: list[str]


class GroupOut(ApiModel):
    id: int
    name: str
    description: str
    members: list[int]
    grants: dict[str, str]


class AccessUserOut(ApiModel):
    id: int
    username: str
    role: str
    active: bool
    name: str
    groups: list[int]
    grants: dict[str, str]
    effective: list[str]


class AccessCatalogOut(ApiModel):
    permissions: list[dict[str, Any]]   # каталог прав из манифестов модулей
    roles: list[RoleOut]
    groups: list[GroupOut]
    users: list[AccessUserOut]


class RoleCreatedOut(ApiModel):
    ok: bool = True
    role: str


class GroupCreatedOut(ApiModel):
    id: int
