"""Текущая сессия пользователя (токен в cookie → запись в user_sessions): Principal и его разрешение.

Ядро (R5) не импортирует модели модулей: сотрудника загружает функция, которую подключает
bootstrap (set_employee_loader). Права — в core/permissions.py, страж иерархии ролей — в
core/auth_guards.py, журнал — в core/audit.py.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from .config import settings
from .db import get_db
from .identity import User
from .roles import ROLE_ADMIN, ROLE_EMPLOYEE, ROLE_MANAGER, ROLE_SUPERVISOR
from .sessions import find_session


@dataclass
class Principal:
    user: User
    employee: Optional[Any]       # people.Employee — ядро не знает модели модулей
    impersonated: bool = False
    session_id: Optional[int] = None   # запись user_sessions, по которой вошли (None — Principal собран не из cookie)

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
    row = find_session(db, token)
    if row is None:
        raise _unauthorized()
    user = db.get(User, row.user_id)
    if not user or not user.is_active:
        raise _unauthorized()
    employee = None
    if row.employee_id and _EMPLOYEE_LOADER is not None:
        employee = _EMPLOYEE_LOADER(db, row.employee_id)
    if row.impersonated and (employee is None or not employee.active):
        raise _unauthorized()          # «как сотрудник» за уволенного/удалённого — сессия кончилась
    return Principal(user=user, employee=employee, impersonated=row.impersonated, session_id=row.id)


def optional_principal(request: Request, db: Session = Depends(get_db)) -> Optional[Principal]:
    try:
        return current_principal(request, db)
    except HTTPException:
        return None


# Права проверяет единственная зависимость require_perm("<ключ>") из core/permissions.py по
# каталогу PERMISSIONS; роль вне ядра прав не читает никто (страж:
# tests/test_permissions_unification.py). Property Principal.is_manager — утилита ролевой
# иерархии (рядом с can_manage_user в core/auth_guards.py), для прав экранов её использовать
# не следует. can_manage_user — в core/auth_guards.py, audit() — в core/audit.py.
