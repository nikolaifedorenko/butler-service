"""Текущая сессия пользователя (подписанная cookie): Principal и его разрешение.

Ядро (R5): не импортирует модели каталога — Employee ищется по строковому имени
сущности через реестр SQLAlchemy (`db.get("Employee", …)`), аннотация — под
TYPE_CHECKING. Права — в core/permissions.py, страж иерархии ролей — в
core/auth_guards.py, журнал — в core/audit.py (фаза C1, 20.10.2026).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from .config import settings
from .db import get_db
from .identity import User
from .roles import ROLE_ADMIN, ROLE_EMPLOYEE, ROLE_MANAGER, ROLE_SUPERVISOR
from .security import read_token

if TYPE_CHECKING:
    from app.modules.employees.application.catalog import Employee


@dataclass
class Principal:
    user: User
    employee: Optional[Employee]
    impersonated: bool = False

    @property
    def role(self) -> str:
        # в режиме «смотрю как сотрудник» права — ровно как у сотрудника
        return ROLE_EMPLOYEE if self.impersonated else self.user.role

    @property
    def is_manager(self) -> bool:
        return self.role in (ROLE_ADMIN, ROLE_MANAGER, ROLE_SUPERVISOR)

    @property
    def is_admin(self) -> bool:
        return self.role == ROLE_ADMIN

    @property
    def name(self) -> str:
        if self.employee:
            return self.employee.full_name
        return self.user.username

    @property
    def actor_label(self) -> str:
        """Автор действия для журналов и историй: «как сотрудник» — кто вошёл на самом деле
        (решение владельца В-3: действовать в этом режиме можно, но с пометкой)."""
        return f"{self.user.username} → как {self.name}" if self.impersonated else self.name

    def to_dict(self) -> dict:
        return {
            "id": self.user.id,
            "username": self.user.username,
            "role": self.role,
            "name": self.name,
            "employee_id": self.employee.id if self.employee else None,
            "impersonated": self.impersonated,
        }


# Загрузчик Employee внедряется bootstrap'ом (R5: core не импортирует модели
# каталога; аннотация Principal.employee — TYPE_CHECKING, строковая):
# set_employee_loader(fn), fn(db, pk) -> Employee | None.
_EMPLOYEE_LOADER = None


def set_employee_loader(fn) -> None:
    """Регистрирует загрузчик сотрудника по pk (composition root, bootstrap/registry)."""
    global _EMPLOYEE_LOADER
    _EMPLOYEE_LOADER = fn


def _unauthorized() -> HTTPException:
    return HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Требуется вход в систему")


def current_principal(request: Request, db: Session = Depends(get_db)) -> Principal:
    token = request.cookies.get(settings.cookie_name)
    if not token:
        raise _unauthorized()
    payload = read_token(token)
    if not payload:
        raise _unauthorized()
    user = db.get(User, payload.get("uid"))
    if not user or not user.is_active:
        raise _unauthorized()
    # смена пароля увеличивает token_version → старые cookie (в т.ч. украденные) перестают работать
    if int(payload.get("tv", 0)) != int(user.token_version or 0):
        raise _unauthorized()
    employee = None
    emp_id = payload.get("emp_id")
    if emp_id and _EMPLOYEE_LOADER is not None:
        employee = _EMPLOYEE_LOADER(db, emp_id)
    if payload.get("imp") and (employee is None or not employee.active):
        raise _unauthorized()          # «как сотрудник» за уволенного/удалённого — сессия кончилась
    return Principal(user=user, employee=employee, impersonated=bool(payload.get("imp")))


def optional_principal(request: Request, db: Session = Depends(get_db)) -> Optional[Principal]:
    try:
        return current_principal(request, db)
    except HTTPException:
        return None


# Ролевые зависимости require_manager/require_supervisor/require_admin удалены
# (этап B унификации прав, 20.10.2026 — см. docs/archive/EXECUTION-SPEC-v2.md §5.2):
# единственный вход проверки прав — require_perm("<ключ>") из core/permissions.py.
# Inline-ветвления «менеджерской видимости» переведены на ключи каталога
# (батч 20.10.2026: fact.view_all, punches.view_all/punch_for_others/backfill,
# schedule.view_all/edit), последние восемь ролевых проверок — на employees.bank,
# settings.doublepay, cars.override, cars.maintenance, night.reopen_any, media.delete_any
# (AUTHZ-05, 22.10.2026). Вне ядра прав роль не читает никто (страж:
# tests/test_permissions_unification.py). Свойство Principal.is_manager
# сохранено как утилита ролевой иерархии (рядом с can_manage_user в
# core/auth_guards.py) и для совместимости; для прав экранов его использовать
# не следует — только каталог PERMISSIONS. can_manage_user переехал в
# core/auth_guards.py, audit() — в core/audit.py (фаза C1, 20.10.2026).
