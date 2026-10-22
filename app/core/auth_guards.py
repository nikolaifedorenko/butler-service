"""Страж иерархии ролей: can_manage_user (ядро, R5).

Это НЕ право из каталога PERMISSIONS, а правило анти-эскалации: нельзя создать или изменить
учётку с ролью выше той, что разрешено назначать. С 22.10.2026 (ADR-0011) уровни ролей —
данные таблицы roles: rank роли и max_assignable_rank её обладателя. Задокументированное
исключение ADR-0006 (бросает HTTPException напрямую) сохранено.
"""
from __future__ import annotations

from typing import Optional

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .auth import Principal
from .identity import Role, User


def can_manage_user(db: Session, principal: Principal, target_user: Optional[User],
                    new_role: Optional[str] = None) -> None:
    """Можно ли управлять учёткой target_user и назначать ей new_role.

    Разрешено, если уровень роли цели и назначаемой роли не выше max_assignable_rank роли
    действующего. Встроенные уровни повторяют прежние правила: admin — всё; manager — всё,
    кроме admin; supervisor — только employee; employee — ничего. Неизвестная роль — 422.
    """
    roles = {r.code: r for r in db.scalars(select(Role))}
    if new_role is not None and new_role not in roles:
        raise HTTPException(status_code=422, detail=f"Неизвестная роль пользователя: {new_role}")
    mine = roles.get(principal.role)
    limit = mine.max_assignable_rank if mine else -1
    if limit < 0:
        raise HTTPException(status_code=403, detail="Недостаточно прав: управление учётными записями")
    if target_user is not None:
        target = roles.get(target_user.role)
        if target is not None and target.rank > limit:
            raise HTTPException(status_code=403,
                                detail=f"Изменять учётную запись с ролью «{target.title}» вам нельзя")
    if new_role is not None and roles[new_role].rank > limit:
        raise HTTPException(status_code=403,
                            detail=f"Назначать роль «{roles[new_role].title}» вам нельзя")


def roles_catalog(db: Session) -> list[Role]:
    """Все роли: от старшей к младшей."""
    return list(db.scalars(select(Role).order_by(Role.rank.desc(), Role.title)))


def assignable_roles(db: Session, principal: Principal) -> list[str]:
    """Коды ролей, которые principal может назначать (то же правило, что can_manage_user)."""
    roles = roles_catalog(db)
    limit = next((r.max_assignable_rank for r in roles if r.code == principal.role), -1)
    return [r.code for r in roles if r.rank <= limit]
