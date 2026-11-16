"""API экрана «Права доступа»: права ролей, свои роли, группы, индивидуальные права.
Правила — в ``application/rights.py``."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.auth import Principal
from app.core.db import get_db
from app.core.permissions import require_perm
from app.core.schemas import Ok

from ..application import rights
from ..application.rights import GrantsIn, GroupIn, MembersIn, RoleIn
from .schemas import AccessCatalogOut, GroupCreatedOut, RoleCreatedOut

router = APIRouter(prefix="/api/access", tags=["access"])
MANAGE = require_perm("access.manage")


@router.get("", response_model=AccessCatalogOut)
def catalog(principal: Principal = Depends(MANAGE), db: Session = Depends(get_db)):
    return rights.catalog(db)


@router.post("/roles", response_model=RoleCreatedOut)
def create_role(payload: RoleIn, principal: Principal = Depends(MANAGE), db: Session = Depends(get_db)):
    """Своя роль: права ей выдаются отдельно."""
    return {"role": rights.create_role(db, principal, payload)}


@router.put("/roles/{code}/settings", response_model=Ok)
def update_role(code: str, payload: RoleIn, principal: Principal = Depends(MANAGE), db: Session = Depends(get_db)):
    rights.update_role(db, principal, code, payload)
    return Ok()


@router.delete("/roles/{code}", response_model=Ok)
def delete_role(code: str, principal: Principal = Depends(MANAGE), db: Session = Depends(get_db)):
    rights.delete_role(db, principal, code)
    return Ok()


@router.put("/roles/{role}", response_model=Ok)
def put_role(role: str, payload: GrantsIn, principal: Principal = Depends(MANAGE), db: Session = Depends(get_db)):
    """Права роли сверх прав по умолчанию."""
    rights.put_role(db, principal, role, payload)
    return Ok()


@router.post("/groups", response_model=GroupCreatedOut)
def create_group(payload: GroupIn, principal: Principal = Depends(MANAGE), db: Session = Depends(get_db)):
    return {"id": rights.create_group(db, principal, payload)}


@router.put("/groups/{group_id}", response_model=Ok)
def update_group(group_id: int, payload: GroupIn, principal: Principal = Depends(MANAGE),
                 db: Session = Depends(get_db)):
    rights.update_group(db, principal, group_id, payload)
    return Ok()


@router.delete("/groups/{group_id}", response_model=Ok)
def delete_group(group_id: int, principal: Principal = Depends(MANAGE), db: Session = Depends(get_db)):
    rights.delete_group(db, principal, group_id)
    return Ok()


@router.put("/groups/{group_id}/grants", response_model=Ok)
def put_group_grants(group_id: int, payload: GrantsIn, principal: Principal = Depends(MANAGE),
                     db: Session = Depends(get_db)):
    rights.put_group_grants(db, principal, group_id, payload)
    return Ok()


@router.put("/groups/{group_id}/members", response_model=Ok)
def put_members(group_id: int, payload: MembersIn, principal: Principal = Depends(MANAGE),
                db: Session = Depends(get_db)):
    rights.put_members(db, principal, group_id, payload)
    return Ok()


@router.put("/users/{user_id}/grants", response_model=Ok)
def put_user_grants(user_id: int, payload: GrantsIn, principal: Principal = Depends(MANAGE),
                    db: Session = Depends(get_db)):
    rights.put_user_grants(db, principal, user_id, payload)
    return Ok()
