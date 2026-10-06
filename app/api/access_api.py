"""Права доступа: базовые права ролей, группы доступа, индивидуальные права пользователей."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..auth import Principal, audit
from ..db import get_db
from ..models import AccessGrant, AccessGroup, AccessGroupMember, User
from ..permissions import (ALL_KEYS, PERMISSIONS, ROLE_DEFAULTS, ROLE_TITLES, effective_permissions,
                           require_perm, role_permissions)

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
    return {
        "permissions": PERMISSIONS,
        "roles": [{"role": r, "title": ROLE_TITLES[r], "defaults": sorted(ROLE_DEFAULTS[r]),
                   "overrides": _grants(db.scalars(select(AccessGrant).where(AccessGrant.role == r))),
                   "effective": sorted(role_permissions(db, r))} for r in ROLE_DEFAULTS],
        "groups": [{"id": g.id, "name": g.name, "description": g.description, "members": members.get(g.id, []),
                    "grants": _grants(db.scalars(select(AccessGrant).where(AccessGrant.group_id == g.id)))}
                   for g in groups],
        "users": [{"id": u.id, "username": u.username, "role": u.role, "active": u.is_active,
                   "name": u.employee.full_name if u.employee else u.username,
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


@router.put("/roles/{role}")
def put_role(role: str, payload: GrantsIn, principal: Principal = Depends(require_perm("access.manage")),
             db: Session = Depends(get_db)):
    if role not in ROLE_DEFAULTS:
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
    before = {"name": g.name, "description": g.description}
    g.name, g.description = payload.name.strip() or g.name, payload.description.strip()
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
    db.execute(delete(AccessGroupMember).where(AccessGroupMember.group_id == group_id))
    ids = sorted(set(payload.user_ids))
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
