"""Права доступа: базовые права ролей, группы доступа, индивидуальные права пользователей."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.audit import audit
from app.core.auth import Principal
from app.core.db import get_db
from app.core.identity import AccessGrant, AccessGroup, AccessGroupMember, Role, User
from app.core.permissions import (
    ALL_KEYS,
    PERMISSIONS,
    ROLE_DEFAULTS,
    effective_permissions,
    require_perm,
    role_permissions,
)

router = APIRouter(prefix="/api/access", tags=["access"])
EFFECTS = ("allow", "deny")


def _grants(rows) -> dict:
    return {g.permission: g.effect for g in rows}


@router.get("")
def catalog(principal: Principal = Depends(require_perm("access.manage")), db: Session = Depends(get_db)):
    groups = list(db.scalars(select(AccessGroup).order_by(AccessGroup.name)))
    members: dict[int, list[int]] = {}
    for m in db.scalars(select(AccessGroupMember)):
        members.setdefault(m.group_id, []).append(m.user_id)
    users = list(db.scalars(select(User).order_by(User.username)))
    # R6 (батч 20.10.2026): User.employee (core→модуль) удалён — сотрудники
    # пользователей одним батч-запросом через границу employees.application.
    from app.modules.employees.application import Employee

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
        raise HTTPException(status_code=422, detail=f"Неизвестные права или значения: {', '.join(bad)}")
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
        raise HTTPException(status_code=422, detail="Укажите название роли")
    if not 0 < payload.rank < 100:
        raise HTTPException(status_code=422, detail="Уровень своей роли — от 1 до 99 (100 — администратор)")
    if not -1 <= payload.max_assignable_rank <= payload.rank:
        raise HTTPException(status_code=422,
                            detail="Роль не может назначать роли выше своего уровня")
    if db.scalar(select(Role).where(Role.title == title, Role.code != code)):
        raise HTTPException(status_code=409, detail="Роль с таким названием уже есть")
    return title


@router.post("/roles")
def create_role(payload: RoleIn, principal: Principal = Depends(require_perm("access.manage")),
                db: Session = Depends(get_db)):
    """Своя роль (ADR-0011): права по умолчанию пустые — выдаются в «Правах доступа»."""
    title = _check_role(db, payload)
    taken = set(db.scalars(select(Role.code)))
    code = next(f"role_{n}" for n in range(1, len(taken) + 2) if f"role_{n}" not in taken)
    db.add(Role(code=code, title=title, rank=payload.rank,
                max_assignable_rank=payload.max_assignable_rank, builtin=False))
    audit(db, principal, "access_role_create", f"role:{code}", payload.model_dump())
    db.commit()
    return {"ok": True, "role": code}


def _custom_role(db: Session, code: str) -> Role:
    role = db.get(Role, code)
    if role is None:
        raise HTTPException(status_code=404, detail="Неизвестная роль")
    if role.builtin:
        raise HTTPException(status_code=409, detail="Встроенную роль менять и удалять нельзя — только её права")
    return role


@router.put("/roles/{code}/settings")
def update_role(code: str, payload: RoleIn, principal: Principal = Depends(require_perm("access.manage")),
                db: Session = Depends(get_db)):
    role = _custom_role(db, code)
    role.title = _check_role(db, payload, code)
    role.rank, role.max_assignable_rank = payload.rank, payload.max_assignable_rank
    audit(db, principal, "access_role_update", f"role:{code}", payload.model_dump())
    db.commit()
    return {"ok": True}


@router.delete("/roles/{code}")
def delete_role(code: str, principal: Principal = Depends(require_perm("access.manage")),
                db: Session = Depends(get_db)):
    role = _custom_role(db, code)
    used = db.scalar(select(func.count()).select_from(User).where(User.role == code))
    if used:
        raise HTTPException(status_code=409, detail=f"Роль назначена пользователям ({used}) — сначала смените им роль")
    db.execute(delete(AccessGrant).where(AccessGrant.role == code))
    db.delete(role)
    audit(db, principal, "access_role_delete", f"role:{code}", {"title": role.title})
    db.commit()
    return {"ok": True}


@router.put("/roles/{role}")
def put_role(role: str, payload: GrantsIn, principal: Principal = Depends(require_perm("access.manage")),
             db: Session = Depends(get_db)):
    if db.get(Role, role) is None:
        raise HTTPException(status_code=404, detail="Неизвестная роль")
    clean = _replace_grants(db, AccessGrant.role == role,
                            lambda k, v: AccessGrant(role=role, permission=k, effect=v), payload.grants)
    audit(db, principal, "access_role", f"role:{role}", clean)
    db.commit()
    return {"ok": True}


class GroupIn(BaseModel):
    name: str
    description: str = ""


@router.post("/groups")
def create_group(payload: GroupIn, principal: Principal = Depends(require_perm("access.manage")),
                 db: Session = Depends(get_db)):
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="Укажите название группы")
    if db.scalar(select(AccessGroup).where(AccessGroup.name == name)):
        raise HTTPException(status_code=409, detail="Группа с таким названием уже есть")
    g = AccessGroup(name=name, description=payload.description.strip())
    db.add(g)
    db.flush()
    audit(db, principal, "access_group_create", f"group:{g.id}", {"name": name})
    db.commit()
    return {"id": g.id}


@router.put("/groups/{group_id}")
def update_group(group_id: int, payload: GroupIn, principal: Principal = Depends(require_perm("access.manage")),
                 db: Session = Depends(get_db)):
    g = db.get(AccessGroup, group_id)
    if not g:
        raise HTTPException(status_code=404, detail="Группа не найдена")
    name = payload.name.strip() or g.name
    # уникальность имени при переименовании (P1-misc-3): create_group имя проверял,
    # rename — нет, дубль падал в IntegrityError (500)
    if name != g.name and db.scalar(select(AccessGroup).where(
            AccessGroup.name == name, AccessGroup.id != group_id)):
        raise HTTPException(status_code=409, detail="Группа с таким названием уже есть")
    before = {"name": g.name, "description": g.description}
    g.name, g.description = name, payload.description.strip()
    audit(db, principal, "access_group_update", f"group:{g.id}", {"before": before, "after": payload.model_dump()})
    db.commit()
    return {"ok": True}


@router.delete("/groups/{group_id}")
def delete_group(group_id: int, principal: Principal = Depends(require_perm("access.manage")),
                 db: Session = Depends(get_db)):
    g = db.get(AccessGroup, group_id)
    if not g:
        raise HTTPException(status_code=404, detail="Группа не найдена")
    db.execute(delete(AccessGrant).where(AccessGrant.group_id == group_id))
    db.execute(delete(AccessGroupMember).where(AccessGroupMember.group_id == group_id))
    audit(db, principal, "access_group_delete", f"group:{group_id}", {"name": g.name})
    db.delete(g)
    db.commit()
    return {"ok": True}


@router.put("/groups/{group_id}/grants")
def put_group_grants(group_id: int, payload: GrantsIn, principal: Principal = Depends(require_perm("access.manage")),
                     db: Session = Depends(get_db)):
    if not db.get(AccessGroup, group_id):
        raise HTTPException(status_code=404, detail="Группа не найдена")
    clean = _replace_grants(db, AccessGrant.group_id == group_id,
                            lambda k, v: AccessGrant(group_id=group_id, permission=k, effect=v), payload.grants)
    audit(db, principal, "access_group_grants", f"group:{group_id}", clean)
    db.commit()
    return {"ok": True}


class MembersIn(BaseModel):
    user_ids: list[int]


@router.put("/groups/{group_id}/members")
def put_members(group_id: int, payload: MembersIn, principal: Principal = Depends(require_perm("access.manage")),
                db: Session = Depends(get_db)):
    if not db.get(AccessGroup, group_id):
        raise HTTPException(status_code=404, detail="Группа не найдена")
    ids = sorted(set(payload.user_ids))
    # FK user_id — валидны ДО перезаписи состава (P1-misc-3): битый id на
    # PostgreSQL давал IntegrityError (500), на SQLite — участника-призрака
    if ids:
        found = set(db.scalars(select(User.id).where(User.id.in_(ids))))
        missing = [i for i in ids if i not in found]
        if missing:
            raise HTTPException(status_code=422,
                                detail=f"Пользователи не найдены: {', '.join(map(str, missing))}")
    db.execute(delete(AccessGroupMember).where(AccessGroupMember.group_id == group_id))
    db.add_all([AccessGroupMember(group_id=group_id, user_id=u) for u in ids])
    audit(db, principal, "access_group_members", f"group:{group_id}", {"user_ids": ids})
    db.commit()
    return {"ok": True}


@router.put("/users/{user_id}/grants")
def put_user_grants(user_id: int, payload: GrantsIn, principal: Principal = Depends(require_perm("access.manage")),
                    db: Session = Depends(get_db)):
    u = db.get(User, user_id)
    if not u:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    if u.id == principal.user.id and payload.grants.get("access.manage") == "deny":
        raise HTTPException(status_code=409, detail="Нельзя снять с себя право управления доступом")
    clean = _replace_grants(db, AccessGrant.user_id == user_id,
                            lambda k, v: AccessGrant(user_id=user_id, permission=k, effect=v), payload.grants)
    audit(db, principal, "access_user_grants", f"user:{u.username}", clean)
    db.commit()
    return {"ok": True}
