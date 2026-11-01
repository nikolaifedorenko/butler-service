"""API профилей гостей (§3.2, §8): список с фамилиями — stays.view, карточка целиком —
stays.guests, запись — stays.edit. Изменения — в журнале аудита с разницей полей.
Вкладка «Гости» (addendum §3): справочник с фильтрами, история проживаний, объединение дублей."""
from __future__ import annotations

import datetime as dt
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.audit import audit
from app.core.auth import Principal
from app.core.db import get_db
from app.core.permissions import require_perm

from ..adapters.orm import Guest
from ..application import family, guests, guests_list, history, mine
from ..application.fund import FundConflict, FundError
from ..application.visibility import at_least, level_for
from ._ops import PREVIEW, run

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


class NewGuestIn(BaseModel):
    last_name: str = Field(min_length=1, max_length=80)
    first_name: str = Field("", max_length=80)
    gender: Literal["m", "f", ""] = ""


class LinkIn(BaseModel):
    """parent — гость из пути родитель guest_id; former — бывшие супруги. Вторая сторона —
    guest_id (существующий) или new_guest (создаётся в той же записи). other_is_parent — вторая
    сторона родитель гостя из пути; also_parent_id — второй родитель того же ребёнка."""
    guest_id: Optional[int] = None
    new_guest: Optional[NewGuestIn] = None
    kind: str
    former: bool = False
    other_is_parent: bool = False
    also_parent_id: Optional[int] = None


class FormerIn(BaseModel):
    """former — супруги бывшие (true) или действующие (false)."""
    former: bool


class MergeIn(BaseModel):
    """keep_id — кого оставить, drop_id — дубль, который удаляется."""
    keep_id: int
    drop_id: int


def _card(db: Session, g: Guest) -> dict:
    return {**guests.guest_dict(g), "links": guests.links_of(db, g.id)}


@router.get("/guests")
def list_guests(q: str = "", principal: Principal = Depends(require_perm("stays.view")),
                db: Session = Depends(get_db)):
    """Подбор гостя по ФИО, телефону и полям с поиском: без контактов и дат рождения."""
    return [{"id": g.id, "last_name": g.last_name, "first_name": g.first_name,
             "middle_name": g.middle_name, "level": g.level, "short": guests.short_name(g)}
            for g in guests.search_guests(db, q)]


def _require_full(db: Session, principal: Principal) -> None:
    """Вкладка «Гости» и всё, что из неё (addendum §3): только полный уровень — stays.guests
    вместе с доступом к шахматке с фамилиями."""
    if level_for(db, principal) != "full":
        raise HTTPException(status_code=403, detail="Справочник гостей — с правом «Профили гостей целиком»")


@router.get("/guests/list")
def guests_tab(q: str = "", level: Literal["", "regular", "vip", "vvip"] = "",
               stayed_from: Optional[dt.date] = None, stayed_to: Optional[dt.date] = None,
               birthday_days: Optional[int] = Query(None, ge=0, le=guests_list.MAX_BIRTHDAY_DAYS),
               sort: Literal["name", "level", "last_stay", "stays"] = "name", dir: Literal["asc", "desc"] = "asc",
               offset: int = Query(0, ge=0), limit: int = Query(guests_list.MAX_LIMIT, ge=1, le=guests_list.MAX_LIMIT),
               principal: Principal = Depends(require_perm("stays.guests")), db: Session = Depends(get_db)):
    """Вкладка «Гости»: только полный уровень (stays.guests), остальным — 403."""
    _require_full(db, principal)
    try:
        query = guests_list.GuestQuery(q, level, stayed_from, stayed_to, birthday_days, sort, dir, offset, limit)
    except FundError as e:
        raise _err(e) from e
    return guests_list.list_guests(db, query)


@router.post("/guests/merge")
def merge_guests(payload: MergeIn, preview_flag: bool = PREVIEW,
                 principal: Principal = Depends(require_perm("stays.edit")), db: Session = Depends(get_db)):
    """Объединение дублей: ?preview=1 — что перенесётся, тем же кодом с откатом."""
    _require_full(db, principal)

    def op() -> dict:
        out = guests.merge_guests(db, payload.keep_id, payload.drop_id)
        audit(db, principal, "stays_guest_merge", f"guest:{payload.keep_id}",
              {"drop_id": payload.drop_id, "not_carried": out.pop("not_carried"), "moves": out["moves"]})
        return out

    done = run(db, op, preview_flag, None, principal)
    return {"preview": done["preview"], **done["result"], "diff": done["diff"],
            **({"overbook_refused": done["overbook_refused"]} if "overbook_refused" in done else {})}


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


@router.get("/guests/{gid}/stays")
def guest_stays(gid: int, principal: Principal = Depends(require_perm("stays.guests")),
                db: Session = Depends(get_db)):
    """История проживаний гостя: все брони, где он жил, с объектами по фонду дня и батлерами."""
    _require_full(db, principal)
    if db.get(Guest, gid) is None:
        raise HTTPException(status_code=404, detail="Гость не найден")
    return history.guest_stays(db, gid)


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
    """Связь, при необходимости — с новым гостем и вторым родителем: всё одной записью под
    замком модуля; отказ любой проверки — 422, не создаётся ничего."""
    try:
        rows, other = guests.add_links(
            db, gid, payload.kind, other_id=payload.guest_id,
            new_guest=payload.new_guest.model_dump() if payload.new_guest else None, former=payload.former,
            other_is_parent=payload.other_is_parent, also_parent_id=payload.also_parent_id)
    except FundError as e:
        db.rollback()          # новый гость и первая связь уже в flush — откат целиком
        raise _err(e) from e
    if payload.new_guest:
        audit(db, principal, "stays_guest", f"guest:{other}", {"created": payload.new_guest.model_dump()})
    for row in rows:
        audit(db, principal, "stays_guest_link", f"guest:{row.guest_a_id}",
              {"added": {"guest_id": row.guest_b_id, "kind": row.kind, "former": row.former, "link_id": row.id}})
    db.commit()
    return {"id": rows[0].id, "guest_id": other, "ids": [r.id for r in rows]}


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


@router.patch("/guest-links/{link_id}")
def set_link_former(link_id: int, payload: FormerIn, principal: Principal = Depends(require_perm("stays.edit")),
                    db: Session = Depends(get_db)):
    """«Бывшие» на линии супругов в редакторе дерева: снять — только если у обоих нет
    другого действующего супруга (422)."""
    try:
        row, before = guests.set_former(db, link_id, payload.former)
    except FundError as e:
        raise _err(e) from e
    audit(db, principal, "stays_guest_link", f"guest:{row.guest_a_id}",
          {"former": [before, row.former], "guest_id": row.guest_b_id, "link_id": link_id})
    db.commit()
    return {"id": row.id, "former": row.former}


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
