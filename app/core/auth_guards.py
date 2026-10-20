"""Страж иерархии ролей: can_manage_user (ядро, R5).

Вынесено из app/auth.py в фазе C1 (20.10.2026). Это НЕ право из каталога
PERMISSIONS, а правило анти-эскалации: нельзя создать/изменить учётку с ролью
выше своей. Задокументированное исключение ADR-0006 (переходное: бросает
HTTPException напрямую) — сохранено как есть решением EXECUTION-SPEC-v2 §5.2.
"""
from __future__ import annotations

from typing import Optional

from fastapi import HTTPException

from .auth import Principal
from .identity import User
from .roles import ROLE_ADMIN, ROLE_EMPLOYEE, ROLE_MANAGER, ROLE_SUPERVISOR


def can_manage_user(principal: Principal, target_user: Optional[User], new_role: Optional[str] = None) -> None:
    """Правило управления учётными записями: супервайзер работает только с сотрудниками.

    Живёт в слое доступа (а не в одном из API-модулей), чтобы любое новое место,
    где создаются или правятся пользователи, применяло одно и то же правило:
      * admin — без ограничений;
      * manager — управляет учётными записями, но не назначает/не меняет admin;
      * supervisor — не создаёт/изменяет/удаляет supervisor, manager, admin;
      * employee — не управляет учётными записями вовсе.
    Значение роли обязано быть одним из известных (иначе 422).

    Бросает HTTPException(403) при нехватке прав и HTTPException(422) при
    недопустимом значении роли; возвращает None, если операция разрешена.
    """
    if new_role is not None and new_role not in (ROLE_ADMIN, ROLE_MANAGER, ROLE_SUPERVISOR, ROLE_EMPLOYEE):
        raise HTTPException(status_code=422, detail=f"Неизвестная роль пользователя: {new_role}")
    if principal.is_admin:
        return
    if principal.role == ROLE_MANAGER:
        # менеджер управляет учётными записями, но НЕ назначает/не меняет admin —
        # иначе это эскалация прав до access.manage (см. permissions.py)
        if new_role == ROLE_ADMIN:
            raise HTTPException(status_code=403, detail="Назначать роль «admin» может только администратор")
        if target_user is not None and target_user.role == ROLE_ADMIN:
            raise HTTPException(status_code=403,
                                detail="Изменять учётную запись администратора может только администратор")
        return
    if principal.role != ROLE_SUPERVISOR:
        raise HTTPException(status_code=403, detail="Недостаточно прав: управление учётными записями")
    if target_user is not None and target_user.role != ROLE_EMPLOYEE:
        raise HTTPException(status_code=403,
                            detail="Супервайзер не может изменять или удалять supervisor, manager и admin")
    if new_role is not None and new_role != ROLE_EMPLOYEE:
        raise HTTPException(status_code=403,
                            detail="Супервайзер может создавать пользователей только с ролью «employee»")
