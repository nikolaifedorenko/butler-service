"""API броней (§3.3, §4.7, §9): документ брони, статусы с no-show, группы совместного
проживания, блоки и OOO. Каждая операция пересчитывает распределение по объектам и
пишет журнал «было → стало»; устаревшая версия брони — 409."""
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

from ..adapters.orm import Hold, Reservation, StayGroup
from ..application import allocation, coverage, mine, reservations
from ._ops import PREVIEW, run

router = APIRouter(prefix="/api/stays", tags=["stays"])
EDIT = require_perm("stays.edit")


class MoveIn(BaseModel):
    move_date: dt.date
    category_id: int


class OccupantIn(BaseModel):
    id: Optional[int] = None
    guest_id: int
    date_from: dt.date
    date_to: dt.date
    role: Literal["main", "guest"] = "guest"


class CompanionIn(BaseModel):
    kind: str = "other"
    description: str = Field("", max_length=255)


class LogisticsIn(BaseModel):
    kind: str = "transfer"
    date: Optional[dt.date] = None
    time: str = Field("", pattern=r"^(|\d{2}:\d{2})$")
    description: str = Field("", max_length=255)


class ReservationIn(BaseModel):
    number: str = Field("", max_length=40)
    status: Literal["tentative", "confirmed"] = "confirmed"     # только при создании
    check_in: dt.date
    check_out: dt.date
    early: bool = False
    late: bool = False
    category_id: int
    paid_by: str = Field("", max_length=120)
    label_id: Optional[int] = None
    customer: str = Field("", max_length=160)
    purpose: str = Field("", max_length=160)
    note: str = Field("", max_length=4000)
    declined_butler: bool = False
    fields: dict = {}
    group_id: Optional[int] = None
    moves: list[MoveIn] = []
    occupants: list[OccupantIn] = []
    companions: list[CompanionIn] = []
    logistics: list[LogisticsIn] = []
    pins: Optional[dict[int, Optional[int]]] = None              # сегмент → объект; None — «авто»
    version: Optional[int] = None                                 # обязательна при правке


class StatusIn(BaseModel):
    status: str
    version: int
    new_check_in: Optional[dt.date] = None


class GroupIn(BaseModel):
    title: str = Field("", max_length=120)


class HoldIn(BaseModel):
    unit_id: int
    start: dt.date
    end: dt.date
    kind: Literal["block", "ooo"] = "block"
    title: str = Field("", max_length=120)


def _doc(payload: ReservationIn) -> dict:
    return payload.model_dump(exclude={"version"})


def _result(db: Session, r: Reservation) -> dict:
    return reservations.reservation_dict(db, r, allocation.current_state(db))


def _window(r: Reservation | None, *docs) -> tuple[dt.date, dt.date]:
    """Дни, на которые операция может повлиять: старые и новые даты брони."""
    starts = [d["check_in"] for d in docs] + ([r.check_in] if r else [])
    ends = [d["check_out"] for d in docs] + ([r.check_out] if r else [])
    return min(starts), max(max(ends) - dt.timedelta(days=1), min(starts))


def _cleanup(db: Session, principal: Principal, r: Reservation, old_group_id: int | None = None) -> None:
    """Строки покрытия на дни, когда гостей брони уже нет, снимаются с записью в журнал (§4.2)."""
    removed = coverage.cleanup_lines(db, r.id, old_group_id)
    if removed:
        audit(db, principal, "stays_coverage_cleanup", f"reservation:{r.id}", {"days": removed})


@router.post("/reservations")
def create_reservation(payload: ReservationIn, preview_flag: bool = PREVIEW,
                       principal: Principal = Depends(EDIT), db: Session = Depends(get_db)):
    doc = _doc(payload)

    def op():
        r, before = reservations.save_reservation(db, doc, None, None)
        audit(db, principal, "stays_reservation", f"reservation:{r.id}",
              {"diff": reservations.diff_of(before, db, r)})
        return _result(db, r)
    return run(db, op, preview_flag, _window(None, doc))


EDIT_OR_MINE = require_perm("stays.edit", "stays.edit_mine")


def _mine_mode(db: Session, principal: Principal, rid: int) -> bool:
    """Правит батлер по stays.edit_mine (а не менеджер по stays.edit): только свою бронь (§7)."""
    if "stays.edit" in principal.gate_permissions:
        return False
    if principal.employee is None or rid not in mine.owned_reservations(db, principal.employee.id):
        raise HTTPException(status_code=403, detail="Это не ваша бронь: вы не ведёте её гостей")
    return True


@router.get("/reservations/{rid}")
def get_reservation(rid: int, principal: Principal = Depends(EDIT_OR_MINE), db: Session = Depends(get_db)):
    r = db.get(Reservation, rid)
    if r is None:
        raise HTTPException(status_code=404, detail="Бронь не найдена")
    _mine_mode(db, principal, rid)
    return reservations.reservation_dict(db, r)


@router.put("/reservations/{rid}")
def update_reservation(rid: int, payload: ReservationIn, preview_flag: bool = PREVIEW,
                       principal: Principal = Depends(EDIT_OR_MINE), db: Session = Depends(get_db)):
    if payload.version is None:
        raise HTTPException(status_code=422, detail="Не указана версия брони")

    doc = _doc(payload)
    r0 = db.get(Reservation, rid)
    if r0 is not None and _mine_mode(db, principal, rid):
        try:
            mine.check_reservation_change(db, reservations.reservation_dict(db, r0), doc)
        except mine.MineForbidden as e:
            raise HTTPException(status_code=403, detail=str(e)) from e
    window = _window(r0, doc)
    old_group = r0.group_id if r0 else None

    def op():
        r, before = reservations.save_reservation(db, doc, rid, payload.version)
        audit(db, principal, "stays_reservation", f"reservation:{r.id}",
              {"diff": reservations.diff_of(before, db, r)})
        _cleanup(db, principal, r, old_group)
        return _result(db, r)
    return run(db, op, preview_flag, window)


@router.post("/reservations/{rid}/status")
def change_status(rid: int, payload: StatusIn, preview_flag: bool = PREVIEW,
                  principal: Principal = Depends(EDIT), db: Session = Depends(get_db)):
    r0 = db.get(Reservation, rid)
    window = _window(r0) if r0 else None

    def op():
        r, before = reservations.set_status(db, rid, payload.status, payload.version, payload.new_check_in)
        audit(db, principal, "stays_reservation_status", f"reservation:{r.id}",
              {"diff": reservations.diff_of(before, db, r)})
        _cleanup(db, principal, r)
        return _result(db, r)
    return run(db, op, preview_flag, window)


class JoinIn(BaseModel):
    reservation_ids: list[int] = Field(min_length=2, max_length=10)


class LeaveIn(BaseModel):
    reservation_id: int


@router.get("/reservations/{rid}/cohabit")
def cohabit(rid: int, principal: Principal = Depends(EDIT), db: Session = Depends(get_db)):
    try:
        return reservations.cohabit_candidates(db, rid)
    except reservations.ReservationInvalid as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


def _span(rs: list[Reservation]) -> tuple[dt.date, dt.date]:
    return _window(None, *({"check_in": r.check_in, "check_out": r.check_out} for r in rs))


@router.post("/groups/join")
def join_group(payload: JoinIn, preview_flag: bool = PREVIEW, principal: Principal = Depends(EDIT),
               db: Session = Depends(get_db)):
    """Совместное проживание (§3.3): брони — в одну группу, с предпросмотром размещения."""
    found = [r for r in (db.get(Reservation, i) for i in payload.reservation_ids) if r is not None]

    def op():
        gid, saved = reservations.join_group(db, payload.reservation_ids)
        for r, before in saved:
            audit(db, principal, "stays_reservation", f"reservation:{r.id}",
                  {"diff": reservations.diff_of(before, db, r)})
        return {"group_id": gid}
    return run(db, op, preview_flag, _span(found) if found else None)


@router.post("/groups/leave")
def leave_group(payload: LeaveIn, preview_flag: bool = PREVIEW, principal: Principal = Depends(EDIT),
                db: Session = Depends(get_db)):
    r0 = db.get(Reservation, payload.reservation_id)

    def op():
        r, before, old = reservations.leave_group(db, payload.reservation_id)
        audit(db, principal, "stays_reservation", f"reservation:{r.id}", {"diff": reservations.diff_of(before, db, r)})
        _cleanup(db, principal, r, old)
        return _result(db, r)
    return run(db, op, preview_flag, _span([r0]) if r0 else None)


@router.post("/groups")
def create_group(payload: GroupIn, principal: Principal = Depends(EDIT), db: Session = Depends(get_db)):
    g = StayGroup(title=payload.title)
    db.add(g)
    db.flush()
    audit(db, principal, "stays_reservation", f"group:{g.id}", {"title": payload.title})
    db.commit()
    return {"id": g.id, "title": g.title}


def _hold_op(db: Session, principal: Principal, payload: Optional[HoldIn], hid: Optional[int]):
    def op():
        if payload is None:
            before = reservations.delete_hold(db, hid)
            after = {k: None for k in before}
        else:
            h, before = reservations.save_hold(db, payload.model_dump(), hid)
            after = reservations.hold_dict(h)
        audit(db, principal, "stays_hold", f"hold:{after['id'] or hid}",
              {"diff": reservations.changes(before, after)})
        return after
    return op


@router.post("/holds")
def create_hold(payload: HoldIn, preview_flag: bool = PREVIEW, principal: Principal = Depends(EDIT),
                db: Session = Depends(get_db)):
    return run(db, _hold_op(db, principal, payload, None), preview_flag, (payload.start, payload.end))


@router.put("/holds/{hid}")
def update_hold(hid: int, payload: HoldIn, preview_flag: bool = PREVIEW, principal: Principal = Depends(EDIT),
                db: Session = Depends(get_db)):
    return run(db, _hold_op(db, principal, payload, hid), preview_flag, (payload.start, payload.end))


@router.delete("/holds/{hid}")
def remove_hold(hid: int, preview_flag: bool = PREVIEW, principal: Principal = Depends(EDIT),
                db: Session = Depends(get_db)):
    h = db.get(Hold, hid)
    return run(db, _hold_op(db, principal, None, hid), preview_flag, (h.start, h.end) if h else None)
