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
    from ..models import Employee


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
    return Principal(user=user, employee=employee, impersonated=bool(payload.get("imp")))


def optional_principal(request: Request, db: Session = Depends(get_db)) -> Optional[Principal]:
    try:
        return current_principal(request, db)
    except HTTPException:
        return None


# Ролевые зависимости require_manager/require_supervisor/require_admin удалены
# (этап B унификации прав, 20.10.2026 — см. docs/EXECUTION-SPEC-v2.md §5.2):
# единственный вход проверки прав — require_perm("<ключ>") из app/permissions.py.
# Свойство Principal.is_manager сохранено для inline-ветвлений «менеджерской
# видимости» (fact_api, punches, schedule, photos) — их перевод на ключи
# выполняется в модульных фазах (этап C), список — в CHANGES-документе этапа B.


# can_manage_user переехал в core/auth_guards.py, audit() — в core/audit.py
# (фаза C1, 20.10.2026). Ролевые зависимости require_manager/require_supervisor/
# require_admin удалены этапом B: единственный вход прав — require_perm
# ("<ключ>") из core/permissions.py. Свойство Principal.is_manager сохранено
# для inline-ветвлений «менеджерской видимости» (fact_api, punches, schedule,
# photos) — их перевод на ключи выполняется в модульных фазах (этап C).
