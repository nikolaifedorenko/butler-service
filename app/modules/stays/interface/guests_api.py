"""API профилей гостей (§3.2, §8): список с фамилиями — stays.view, карточка целиком —
stays.guests, запись — stays.edit. Изменения — в журнале аудита с разницей полей."""
from __future__ import annotations

import datetime as dt
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.audit import audit
from app.core.auth import Principal
from app.core.db import get_db
from app.core.permissions import require_perm

from ..adapters.orm import Guest
from ..application import family, guests, mine
from ..application.fund import FundConflict, FundError
from ..application.visibility import at_least, level_for

router = APIRouter(prefix="/api/stays", tags=["stays"])


def _err(e: FundError) -> HTTPException:
    return HTTPException(status_code=409 if isinstance(e, FundConflict) else 422, detail=str(e))


class SpecialDate(BaseModel):
    date: dt.date
    what: str = Field(max_length=120)


class GuestIn(BaseModel):
    last_name: str = Field(min_length=1, max_length=80)
    first_name: str = Field("", max_length=80)
    middle_name: str = Field("", max_length=80)
    phone: str = Field("", max_length=40)
    email: str = Field("", max_length=120)
    birth_date: Optional[dt.date] = None
    gender: Literal["m", "f", ""] = ""
    level: Literal["regular", "vip", "vvip"] = "regular"
    preferences: dict[str, str] = {}
    special_dates: list[SpecialDate] = []
    fields: dict = {}
    note: str = Field("", max_length=4000)


class LinkIn(BaseModel):
    """parent — гость из пути родитель guest_id; former — бывшие супруги."""
    guest_id: int
    kind: str
    former: bool = False


def _card(db: Session, g: Guest) -> dict:
    return {**guests.guest_dict(g), "links": guests.links_of(db, g.id)}


@router.get("/guests")
def list_guests(q: str = "", principal: Principal = Depends(require_perm("stays.view")),
                db: Session = Depends(get_db)):
    """Подбор гостя по ФИО, телефону и полям с поиском: без контактов и дат рождения."""
    return [{"id": g.id, "last_name": g.last_name, "first_name": g.first_name,
             "middle_name": g.middle_name, "level": g.level, "short": guests.short_name(g)}
            for g in guests.search_guests(db, q)]


def _own_guest(db: Session, principal: Principal, gid: int, full_perm: str) -> bool:
    """Без full_perm батлер видит и правит только гостей своих броней (§7, stays.edit_mine)."""
    if full_perm in principal.gate_permissions:
        return False
    if principal.employee is None or not mine.owns_guest(db, principal.employee.id, gid):
        raise HTTPException(status_code=403, detail="Это не ваш гость: вы не ведёте его брони")
    return True


@router.get("/guests/{gid}")
def get_guest(gid: int, principal: Principal = Depends(require_perm("stays.guests", "stays.edit_mine")),
              db: Session = Depends(get_db)):
    g = db.get(Guest, gid)
    if g is None:
        raise HTTPException(status_code=404, detail="Гость не найден")
    _own_guest(db, principal, gid, "stays.guests")
    return _card(db, g)


def _save(db: Session, principal: Principal, payload: GuestIn, gid: Optional[int]) -> dict:
    data = payload.model_dump()
    data["special_dates"] = [{"date": d["date"].isoformat(), "what": d["what"]} for d in data["special_dates"]]
    try:
        g, before = guests.save_guest(db, data, gid)
    except FundError as e:
        raise _err(e) from e
    audit(db, principal, "stays_guest", f"guest:{g.id}", {"diff": guests.guest_changes(before, g)})
    db.commit()
    return _card(db, g)


@router.post("/guests")
def create_guest(payload: GuestIn, principal: Principal = Depends(require_perm("stays.edit")),
                 db: Session = Depends(get_db)):
    return _save(db, principal, payload, None)


@router.put("/guests/{gid}")
def update_guest(gid: int, payload: GuestIn, principal: Principal = Depends(require_perm("stays.edit", "stays.edit_mine")),
                 db: Session = Depends(get_db)):
    g = db.get(Guest, gid)
    if g is not None and _own_guest(db, principal, gid, "stays.edit"):
        try:
            mine.check_guest_change(guests.guest_dict(g), payload.model_dump())
        except mine.MineForbidden as e:
            raise HTTPException(status_code=403, detail=str(e)) from e
    return _save(db, principal, payload, gid)


@router.post("/guests/{gid}/links")
def create_link(gid: int, payload: LinkIn, principal: Principal = Depends(require_perm("stays.edit")),
                db: Session = Depends(get_db)):
    try:
        row = guests.add_link(db, gid, payload.guest_id, payload.kind, payload.former)
    except FundError as e:
        raise _err(e) from e
    audit(db, principal, "stays_guest_link", f"guest:{gid}",
          {"added": {"guest_id": payload.guest_id, "kind": payload.kind, "former": payload.former,
                     "link_id": row.id}})
    db.commit()
    return {"id": row.id}


@router.get("/guests/{gid}/family")
def guest_family(gid: int, principal: Principal = Depends(require_perm("stays.view", "stays.occupancy")),
                 db: Session = Depends(get_db)):
    """Семейное дерево (§4): уровень «с фамилиями» и выше; телефоны и даты рождения — только
    полный уровень. Граф — до 3 поколений вверх и вниз и через брак."""
    level = level_for(db, principal)
    if not at_least(level, "names"):
        raise HTTPException(status_code=403, detail="Семейное дерево — с уровня «с фамилиями»")
    if db.get(Guest, gid) is None:
        raise HTTPException(status_code=404, detail="Гость не найден")
    return family.family(db, gid, level)


@router.delete("/guest-links/{link_id}")
def remove_link(link_id: int, principal: Principal = Depends(require_perm("stays.edit")),
                db: Session = Depends(get_db)):
    try:
        row = guests.delete_link(db, link_id)
    except FundError as e:
        raise _err(e) from e
    audit(db, principal, "stays_guest_link", f"guest:{row.guest_a_id}",
          {"removed": {"guest_id": row.guest_b_id, "kind": row.kind, "link_id": link_id}})
    db.commit()
    return {"ok": True}
