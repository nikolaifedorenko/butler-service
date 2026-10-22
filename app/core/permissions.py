"""Права доступа: каталог прав, базовые права ролей, группы и индивидуальные переопределения.

Итоговое право пользователя вычисляется так (сильнее — ниже):
  1. базовые права роли (ROLE_DEFAULTS), с учётом правок роли администратором (AccessGrant.role);
  2. группы доступа пользователя: allow добавляет право, deny — снимает (deny сильнее allow);
  3. индивидуальные права пользователя (AccessGrant.user_id): allow/deny — окончательное решение.
Администратор всегда сохраняет access.manage, чтобы нельзя было «запереть» систему.
"""
from __future__ import annotations

from typing import Iterable, Optional

from fastapi import Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .auth import Principal, current_principal
from .db import get_db
from .identity import AccessGrant, AccessGroupMember
from .manifest import Perm
from .roles import ROLE_ADMIN, ROLE_EMPLOYEE, ROLE_MANAGER, ROLE_SUPERVISOR

# Каталог собирают манифесты модулей (ADR-0012, 22.10.2026): load_catalog() вызывает
# bootstrap/registry.wire(). Объекты заполняются на месте — модули держат на них ссылки.
PERMISSIONS: list[dict] = []
ALL_KEYS: list[str] = []
ROLE_DEFAULTS: dict[str, set[str]] = {ROLE_ADMIN: set(), ROLE_MANAGER: set(),
                                      ROLE_SUPERVISOR: set(), ROLE_EMPLOYEE: set()}


def load_catalog(perms: Iterable[Perm]) -> None:
    """Каталог прав и права ролей по умолчанию из манифестов; администратору — все права."""
    perms = list(perms)
    PERMISSIONS[:] = [{"key": p.key, "section": p.section, "title": p.title} for p in perms]
    ALL_KEYS[:] = [p.key for p in perms]
    for keys in ROLE_DEFAULTS.values():
        keys.clear()
    ROLE_DEFAULTS[ROLE_ADMIN].update(ALL_KEYS)
    for p in perms:
        for role in p.roles:
            ROLE_DEFAULTS[role].add(p.key)




def _apply(perms: set[str], grants: Iterable[AccessGrant]) -> set[str]:
    grants = list(grants)
    allow = {g.permission for g in grants if g.effect == "allow"}
    deny = {g.permission for g in grants if g.effect == "deny"}
    return (perms | allow) - deny


def role_permissions(db: Session, role: str) -> set[str]:
    grants = db.scalars(select(AccessGrant).where(AccessGrant.role == role)).all()
    return _apply(set(ROLE_DEFAULTS.get(role, set())), grants)


def user_group_ids(db: Session, user_id: int) -> list[int]:
    return list(db.scalars(select(AccessGroupMember.group_id).where(AccessGroupMember.user_id == user_id)))


def effective_permissions(db: Session, user_id: int, role: str) -> set[str]:
    perms = role_permissions(db, role)
    gids = user_group_ids(db, user_id)
    if gids:
        perms = _apply(perms, db.scalars(select(AccessGrant).where(AccessGrant.group_id.in_(gids))).all())
    perms = _apply(perms, db.scalars(select(AccessGrant).where(AccessGrant.user_id == user_id)).all())
    if role == ROLE_ADMIN:
        perms.add("access.manage")
    return perms & set(ALL_KEYS)


def principal_permissions(db: Session, principal: Principal) -> set[str]:
    return effective_permissions(db, principal.user.id, principal.role) if not principal.impersonated \
        else role_permissions(db, ROLE_EMPLOYEE)


def has_perm(db: Session, principal: Optional[Principal], key: str) -> bool:
    return bool(principal) and key in principal_permissions(db, principal)


def require_perm(*keys: str):
    """Зависимость FastAPI: нужно хотя бы одно из прав keys."""

    def dep(principal: Principal = Depends(current_principal), db: Session = Depends(get_db)) -> Principal:
        perms = principal_permissions(db, principal)
        if not any(k in perms for k in keys):
            titles = ", ".join(next((p["title"] for p in PERMISSIONS if p["key"] == k), k) for k in keys)
            raise HTTPException(status_code=403, detail=f"Недостаточно прав: {titles}")
        return principal

    return dep
