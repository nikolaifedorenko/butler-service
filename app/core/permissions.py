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
from .roles import ROLE_ADMIN, ROLE_EMPLOYEE, ROLE_MANAGER, ROLE_SUPERVISOR

PERMISSIONS: list[dict] = [
    {"key": "presence.view", "section": "Кто на работе / Посещения", "title": "Просмотр присутствия"},
    {"key": "schedule.view", "section": "График", "title": "Просмотр графика"},
    {"key": "schedule.edit", "section": "График", "title": "Редактирование графика"},
    {"key": "schedule.view_all", "section": "График",
     "title": "Полные данные сетки (заметки и id записей в ячейках)"},
    {"key": "fact.view_all", "section": "Факт",
     "title": "Сессии и сетка «Номера» всех сотрудников"},
    {"key": "tabel.view", "section": "Табель", "title": "Просмотр Табеля"},
    {"key": "tabel.edit", "section": "Табель", "title": "Редактирование Табеля"},
    {"key": "mgmt.view", "section": "Управленческий табель", "title": "Просмотр (view)"},
    {"key": "mgmt.close", "section": "Управленческий табель", "title": "Закрытие периода (close)"},
    {"key": "mgmt.recalculate", "section": "Управленческий табель", "title": "Пересчёт последнего закрытого"},
    {"key": "punches.manage", "section": "Отметки", "title": "Ручные отметки и отмена отметок"},
    # Долг §5.2 закрыт (батч 20.10.2026): inline-ветвления роли is_manager в
    # punches/fact/schedule переведены на ключи каталога. Базовая аудитория —
    # прежняя ролевая (MANAGER_ROLES = admin/manager/supervisor входят в
    # ROLE_DEFAULTS автоматически), поведение ролей не меняется; гранты
    # управляют выдачей/снятием в «Правах доступа».
    {"key": "punches.view_all", "section": "Отметки",
     "title": "Журнал отметок всех сотрудников и комментарии к чужим"},
    {"key": "punches.punch_for_others", "section": "Отметки",
     "title": "Отметка за другого сотрудника"},
    {"key": "punches.backfill", "section": "Отметки",
     "title": "Отметка задним числом (произвольное время)"},
    {"key": "employees.view", "section": "Сотрудники", "title": "Просмотр сотрудников"},
    {"key": "employees.edit", "section": "Сотрудники", "title": "Редактирование сотрудников и банка"},
    # employees.impersonate (этап B, 20.10.2026): «посмотреть глазами сотрудника»
    # было за ролевым require_manager — ключ повторяет прежнюю аудиторию (supervisor+);
    # вторым стражем остаётся can_manage_user (иерархия ролей, анти-эскалация).
    {"key": "employees.impersonate", "section": "Сотрудники", "title": "Войти как сотрудник (имперсонация)"},
    {"key": "settings.view", "section": "Настройки", "title": "Просмотр настроек"},
    {"key": "settings.edit", "section": "Настройки", "title": "Изменение настроек и справочников"},
    {"key": "access.manage", "section": "Права доступа", "title": "Управление правами доступа"},
    {"key": "audit.view", "section": "Журнал аудита", "title": "Просмотр журнала аудита"},
    {"key": "me.punch", "section": "Мои отметки", "title": "Отмечаться «Пришёл/Ушёл»"},
    {"key": "night.view", "section": "Ночной отчёт", "title": "Ночной отчёт"},
    # night.edit (19.10.2026): справочник обхода (зоны, объекты, чек-листы, службы)
    # жил в модалке раздела и проверялся РОЛЬЮ (is_manager) — единственный такой случай.
    # Теперь это ключ каталога: выдаётся/снимается через «Права доступа» как остальные.
    {"key": "night.edit", "section": "Ночной отчёт", "title": "Зоны, объекты, чек-листы, службы"},
    # night.close (этап B, 20.10.2026): закрытие/переоткрытие смены и объектов было
    # за ролевым require_supervisor — ключ повторяет прежнюю аудиторию (supervisor+).
    {"key": "night.close", "section": "Ночной отчёт", "title": "Закрытие и переоткрытие смены/объектов"},
    {"key": "cars.view", "section": "Электрокары", "title": "Просмотр парка и истории"},
    {"key": "cars.use", "section": "Электрокары", "title": "Взять / вернуть / передать кар"},
    {"key": "cars.issue", "section": "Электрокары", "title": "Выдать, закрепить, сменить статус"},
    {"key": "cars.manage", "section": "Электрокары", "title": "Парк и места стоянки: создание, правка, удаление"},
]
ALL_KEYS = [p["key"] for p in PERMISSIONS]

_EMPLOYEE = {"presence.view", "schedule.view", "me.punch", "night.view", "cars.view", "cars.use"}
_SUPERVISOR = set(ALL_KEYS) - {"access.manage", "settings.edit", "mgmt.recalculate", "cars.manage"}
ROLE_DEFAULTS: dict[str, set[str]] = {
    ROLE_ADMIN: set(ALL_KEYS),
    ROLE_MANAGER: set(ALL_KEYS) - {"access.manage"},
    ROLE_SUPERVISOR: _SUPERVISOR,
    ROLE_EMPLOYEE: set(_EMPLOYEE),
}
ROLE_TITLES = {ROLE_ADMIN: "Администратор", ROLE_MANAGER: "Менеджер",
               ROLE_SUPERVISOR: "Старший / супервайзер", ROLE_EMPLOYEE: "Сотрудник"}


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
