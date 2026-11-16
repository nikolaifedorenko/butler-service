"""Права доступа: базовые права ролей, свои роли, группы доступа, индивидуальные права.

Право пользователя складывается из прав роли, групп и личных выдач; запрет сильнее разрешения.
Выдавать можно только то, что есть у самого действующего, и только тем, чьими учётными
записями он управляет по иерархии ролей, — одно правило для пользователя, роли и группы.
Каждая операция — одна транзакция вместе с записью аудита.
"""
from __future__ import annotations

from pydantic import BaseModel
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.audit import audit
from app.core.auth import Principal
from app.core.auth_guards import can_manage_role, can_manage_user
from app.core.db import transactional
from app.core.errors import Conflict, Forbidden, NotFound, Validation
from app.core.identity import AccessGrant, AccessGroup, AccessGroupMember, Role, User
from app.core.permissions import (
    ALL_KEYS,
    PERMISSIONS,
    ROLE_DEFAULTS,
    effective_permissions,
    principal_permissions,
    role_permissions,
)
from app.modules.people.application import Employee

EFFECTS = ("allow", "deny")


def _grants(rows) -> dict:
    return {g.permission: g.effect for g in rows}


def catalog(db: Session) -> dict:
    """Экран «Права доступа»: каталог прав, роли, группы и пользователи с итоговыми правами."""
    groups = list(db.scalars(select(AccessGroup).order_by(AccessGroup.name)))
    members: dict[int, list[int]] = {}
    for m in db.scalars(select(AccessGroupMember)):
        members.setdefault(m.group_id, []).append(m.user_id)
    users = list(db.scalars(select(User).order_by(User.username)))
    emp_ids = {u.employee_id for u in users if u.employee_id}
    emps = {e.id: e for e in db.scalars(select(Employee).where(Employee.id.in_(emp_ids)))} \
        if emp_ids else {}
    return {
        "permissions": PERMISSIONS,
        "roles": [{"role": r.code, "title": r.title, "rank": r.rank,
                   "max_assignable_rank": r.max_assignable_rank, "builtin": r.builtin,
                   "users": sum(1 for u in users if u.role == r.code),
                   "defaults": sorted(ROLE_DEFAULTS.get(r.code, set())),
                   "overrides": _grants(db.scalars(select(AccessGrant).where(AccessGrant.role == r.code))),
                   "effective": sorted(role_permissions(db, r.code))} for r in _roles(db)],
        "groups": [{"id": g.id, "name": g.name, "description": g.description, "members": members.get(g.id, []),
                    "grants": _grants(db.scalars(select(AccessGrant).where(AccessGrant.group_id == g.id)))}
                   for g in groups],
        "users": [{"id": u.id, "username": u.username, "role": u.role, "active": u.is_active,
                   "name": emps[u.employee_id].full_name if u.employee_id in emps else u.username,
                   "groups": [g for g, ms in members.items() if u.id in ms],
                   "grants": _grants(db.scalars(select(AccessGrant).where(AccessGrant.user_id == u.id))),
                   "effective": sorted(effective_permissions(db, u.id, u.role))} for u in users],
    }


class GrantsIn(BaseModel):
    grants: dict[str, str]           # permission → allow | deny | default


def _replace_grants(db: Session, where, make, grants: dict[str, str]) -> dict:
    bad = [k for k, v in grants.items() if k not in ALL_KEYS or v not in (*EFFECTS, "default")]
    if bad:
        raise Validation(f"Неизвестные права или значения: {', '.join(bad)}")
    db.execute(delete(AccessGrant).where(where))
    clean = {k: v for k, v in grants.items() if v in EFFECTS}
    db.add_all([make(k, v) for k, v in clean.items()])
    return clean


def _roles(db: Session) -> list[Role]:
    return list(db.scalars(select(Role).order_by(Role.rank.desc(), Role.title)))


class RoleIn(BaseModel):
    title: str
    rank: int                   # уровень: кто может управлять учётками с этой ролью
    max_assignable_rank: int    # до какого уровня её обладатель управляет учётками (-1 — никого)


def _check_role(db: Session, payload: RoleIn, code: str = "") -> str:
    title = payload.title.strip()
    if not title:
        raise Validation("Укажите название роли")
    if not 0 < payload.rank < 100:
        raise Validation("Уровень своей роли — от 1 до 99 (100 — администратор)")
    if not -1 <= payload.max_assignable_rank <= payload.rank:
        raise Validation("Роль не может назначать роли выше своего уровня")
    if db.scalar(select(Role).where(Role.title == title, Role.code != code)):
        raise Conflict("Роль с таким названием уже есть")
    return title


@transactional
def create_role(db: Session, principal: Principal, payload: RoleIn) -> str:
    """Своя роль: прав по умолчанию у неё нет, они выдаются отдельно. Возвращает код роли."""
    title = _check_role(db, payload)
    taken = set(db.scalars(select(Role.code)))
    code = next(f"role_{n}" for n in range(1, len(taken) + 2) if f"role_{n}" not in taken)
    db.add(Role(code=code, title=title, rank=payload.rank,
                max_assignable_rank=payload.max_assignable_rank, builtin=False))
    audit(db, principal, "access_role_create", f"role:{code}", payload.model_dump())
    return code


def _custom_role(db: Session, code: str) -> Role:
    role = db.get(Role, code)
    if role is None:
        raise NotFound("Неизвестная роль")
    if role.builtin:
        raise Conflict("Встроенную роль менять и удалять нельзя — только её права")
    return role


@transactional
def update_role(db: Session, principal: Principal, code: str, payload: RoleIn) -> None:
    role = _custom_role(db, code)
    role.title = _check_role(db, payload, code)
    role.rank, role.max_assignable_rank = payload.rank, payload.max_assignable_rank
    audit(db, principal, "access_role_update", f"role:{code}", payload.model_dump())


@transactional
def delete_role(db: Session, principal: Principal, code: str) -> None:
    role = _custom_role(db, code)
    used = db.scalar(select(func.count()).select_from(User).where(User.role == code))
    if used:
        raise Conflict(f"Роль назначена пользователям ({used}) — сначала смените им роль")
    db.execute(delete(AccessGrant).where(AccessGrant.role == code))
    db.delete(role)
    audit(db, principal, "access_role_delete", f"role:{code}", {"title": role.title})


@transactional
def put_role(db: Session, principal: Principal, role: str, payload: GrantsIn) -> None:
    target = db.get(Role, role)
    if target is None:
        raise NotFound("Неизвестная роль")
    can_manage_role(db, principal, target)
    _guard_widening(db, principal, AccessGrant.role == role, payload.grants)
    clean = _replace_grants(db, AccessGrant.role == role,
                            lambda k, v: AccessGrant(role=role, permission=k, effect=v), payload.grants)
    audit(db, principal, "access_role", f"role:{role}", clean)


class GroupIn(BaseModel):
    name: str
    description: str = ""


@transactional
def create_group(db: Session, principal: Principal, payload: GroupIn) -> int:
    name = payload.name.strip()
    if not name:
        raise Validation("Укажите название группы")
    if db.scalar(select(AccessGroup).where(AccessGroup.name == name)):
        raise Conflict("Группа с таким названием уже есть")
    g = AccessGroup(name=name, description=payload.description.strip())
    db.add(g)
    db.flush()
    audit(db, principal, "access_group_create", f"group:{g.id}", {"name": name})
    return g.id


@transactional
def update_group(db: Session, principal: Principal, group_id: int, payload: GroupIn) -> None:
    g = db.get(AccessGroup, group_id)
    if not g:
        raise NotFound("Группа не найдена")
    name = payload.name.strip() or g.name
    if name != g.name and db.scalar(select(AccessGroup).where(
            AccessGroup.name == name, AccessGroup.id != group_id)):
        raise Conflict("Группа с таким названием уже есть")
    before = {"name": g.name, "description": g.description}
    g.name, g.description = name, payload.description.strip()
    audit(db, principal, "access_group_update", f"group:{g.id}", {"before": before, "after": payload.model_dump()})


@transactional
def delete_group(db: Session, principal: Principal, group_id: int) -> None:
    g = db.get(AccessGroup, group_id)
    if not g:
        raise NotFound("Группа не найдена")
    # удаление выводит из группы всех участников — те же правила, что для состава
    _guard_members(db, principal, group_id, set())
    db.execute(delete(AccessGrant).where(AccessGrant.group_id == group_id))
    db.execute(delete(AccessGroupMember).where(AccessGroupMember.group_id == group_id))
    audit(db, principal, "access_group_delete", f"group:{group_id}", {"name": g.name})
    db.delete(g)


@transactional
def put_group_grants(db: Session, principal: Principal, group_id: int, payload: GrantsIn) -> None:
    if not db.get(AccessGroup, group_id):
        raise NotFound("Группа не найдена")
    # права группы действуют на всех её участников — каждым надо уметь управлять
    for u in db.scalars(select(User).join(AccessGroupMember, AccessGroupMember.user_id == User.id)
                        .where(AccessGroupMember.group_id == group_id)):
        can_manage_user(db, principal, u)
    _guard_widening(db, principal, AccessGrant.group_id == group_id, payload.grants)
    clean = _replace_grants(db, AccessGrant.group_id == group_id,
                            lambda k, v: AccessGrant(group_id=group_id, permission=k, effect=v), payload.grants)
    audit(db, principal, "access_group_grants", f"group:{group_id}", clean)


class MembersIn(BaseModel):
    user_ids: list[int]


@transactional
def put_members(db: Session, principal: Principal, group_id: int, payload: MembersIn) -> None:
    if not db.get(AccessGroup, group_id):
        raise NotFound("Группа не найдена")
    ids = sorted(set(payload.user_ids))
    # пользователи проверяются до перезаписи состава
    if ids:
        found = set(db.scalars(select(User.id).where(User.id.in_(ids))))
        missing = [i for i in ids if i not in found]
        if missing:
            raise Validation(f"Пользователи не найдены: {', '.join(map(str, missing))}")
    _guard_members(db, principal, group_id, set(ids))
    db.execute(delete(AccessGroupMember).where(AccessGroupMember.group_id == group_id))
    db.add_all([AccessGroupMember(group_id=group_id, user_id=u) for u in ids])
    audit(db, principal, "access_group_members", f"group:{group_id}", {"user_ids": ids})


def _raise_widened(keys: set[str]) -> None:
    if keys:
        titles = {p["key"]: p["title"] for p in PERMISSIONS}
        listed = ", ".join(f"«{titles.get(k, k)}» ({k})" for k in sorted(keys))
        raise Forbidden(f"Нельзя выдать право, которого нет у вас: {listed}")


def _guard_widening(db: Session, principal: Principal, where, grants: dict[str, str]) -> None:
    """Права нельзя расширить сверх своих: новое allow
    либо снятие deny с права, которого у действующего нет. Уже стоящие выдачи (например,
    от администратора) не мешают править остальное. Одно правило для пользователя, роли
    и группы — иначе ограничение обходилось бы через соседнюю вкладку «Доступа»."""
    before = {g.permission: g.effect for g in db.scalars(select(AccessGrant).where(where))}
    after = {k: v for k, v in grants.items() if v in EFFECTS}
    mine = principal_permissions(db, principal)
    _raise_widened({k for k in set(before) | set(after) if k not in mine and (
        (after.get(k) == "allow" and before.get(k) != "allow")
        or (before.get(k) == "deny" and after.get(k) != "deny"))})


def _guard_members(db: Session, principal: Principal, group_id: int, ids: set[int]) -> None:
    """Состав группы — тоже выдача прав: вошедший получает её allow, вышедший теряет её deny.
    Менять состав можно только для тех, чьими учётками действующий управляет."""
    before = set(db.scalars(select(AccessGroupMember.user_id).where(AccessGroupMember.group_id == group_id)))
    added, removed = ids - before, before - ids
    if not added and not removed:
        return
    for u in db.scalars(select(User).where(User.id.in_(added | removed))):
        can_manage_user(db, principal, u)
    grants = list(db.scalars(select(AccessGrant).where(AccessGrant.group_id == group_id)))
    mine = principal_permissions(db, principal)
    _raise_widened({g.permission for g in grants if g.permission not in mine and (
        (g.effect == "allow" and added) or (g.effect == "deny" and removed))})


@transactional
def put_user_grants(db: Session, principal: Principal, user_id: int, payload: GrantsIn) -> None:
    u = db.get(User, user_id)
    if not u:
        raise NotFound("Пользователь не найден")
    if u.id == principal.user.id and payload.grants.get("access.manage") == "deny":
        raise Conflict("Нельзя снять с себя право управления доступом")
    # индивидуальные права — по иерархии учёток: ранг цели как в can_manage_user
    can_manage_user(db, principal, u)
    _guard_widening(db, principal, AccessGrant.user_id == user_id, payload.grants)
    clean = _replace_grants(db, AccessGrant.user_id == user_id,
                            lambda k, v: AccessGrant(user_id=user_id, permission=k, effect=v), payload.grants)
    audit(db, principal, "access_user_grants", f"user:{u.username}", clean)
