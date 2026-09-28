"""Текущая сессия пользователя (подписанная cookie) и права доступа."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from .config import settings
from .db import get_db
from .models import ROLE_ADMIN, ROLE_EMPLOYEE, ROLE_MANAGER, ROLE_SUPERVISOR, Employee, User, utcnow
from .security import read_token


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
    if emp_id:
        employee = db.get(Employee, emp_id)
    return Principal(user=user, employee=employee, impersonated=bool(payload.get("imp")))


def optional_principal(request: Request, db: Session = Depends(get_db)) -> Optional[Principal]:
    try:
        return current_principal(request, db)
    except HTTPException:
        return None


def require_manager(principal: Principal = Depends(current_principal)) -> Principal:
    if not principal.is_manager:
        raise HTTPException(status_code=403, detail="Недостаточно прав: раздел для менеджеров и старших")
    return principal


def require_admin(principal: Principal = Depends(current_principal)) -> Principal:
    if not principal.is_admin:
        raise HTTPException(status_code=403, detail="Недостаточно прав: только администратор")
    return principal


def require_supervisor(principal: Principal = Depends(current_principal)) -> Principal:
    """Супервайзер и выше (supervisor / manager / admin) — закрытие и переоткрытие смен,
    закрепление электрокаров, ручные операции над чужими карами."""
    if principal.role not in (ROLE_ADMIN, ROLE_MANAGER, ROLE_SUPERVISOR):
        raise HTTPException(status_code=403, detail="Недостаточно прав: раздел для супервайзера и старших")
    return principal


def can_manage_user(principal: Principal, target_user: Optional[User], new_role: Optional[str] = None) -> None:
    """Правило управления учётными записями: супервайзер работает только с сотрудниками.

    Живёт в слое доступа (а не в одном из API-модулей), чтобы любое новое место,
    где создаются или правятся пользователи, применяло одно и то же правило:
      * admin / manager — без ограничений;
      * supervisor — не создаёт/изменяет/удаляет supervisor, manager, admin;
      * employee — не управляет учётными записями вовсе.

    Бросает HTTPException(403); возвращает None, если операция разрешена.
    """
    if principal.is_admin or principal.role == ROLE_MANAGER:
        return
    if principal.role != ROLE_SUPERVISOR:
        raise HTTPException(status_code=403, detail="Недостаточно прав: управление учётными записями")
    if target_user is not None and target_user.role != ROLE_EMPLOYEE:
        raise HTTPException(status_code=403,
                            detail="Супервайзер не может изменять или удалять supervisor, manager и admin")
    if new_role is not None and new_role != ROLE_EMPLOYEE:
        raise HTTPException(status_code=403,
                            detail="Супервайзер может создавать пользователей только с ролью «employee»")


def audit(db: Session, principal: Optional[Principal], action: str, target: str = "", payload: Optional[dict] = None) -> None:
    """Запись в журнал аудита (без commit — вызывающий код сам коммитит)."""
    import json

    from .models import AuditLog

    db.add(AuditLog(
        actor_id=principal.user.id if principal else None,
        actor_name=(principal.name + (" (как сотрудник)" if principal.impersonated else "")) if principal else "system",
        action=action, target=target, payload_json=json.dumps(payload or {}, ensure_ascii=False, default=str),
        ts=utcnow(),
    ))
