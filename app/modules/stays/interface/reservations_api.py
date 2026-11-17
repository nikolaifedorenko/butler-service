"""API броней (§3.3, §4.7, §9): документ брони, статусы с no-show, группы совместного
проживания. Каждая операция пересчитывает распределение по объектам и пишет журнал
«было → стало»; устаревшая версия брони — 409.

Правила — в прикладном слое: ``application/reservation_edit.py``. Роутер разбирает запрос и
проверяет право эндпоинта.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.auth import Principal
from app.core.db import get_db
from app.core.permissions import require_perm

from ..adapters.duty_timesheet import TimesheetDuty
from ..application import reservation_edit
from ..application.reservation_forms import GroupIn, JoinIn, LeaveIn, ReservationIn, StatusIn
from ._ops import PREVIEW
from .schemas import (
    CohabitCandidateOut,
    GroupJoinedOut,
    PreviewedOut,
    ReservationDocOut,
    StayGroupOut,
)

router = APIRouter(prefix="/api/stays", tags=["stays"])
EDIT = require_perm("stays.edit")
READ_OR_MINE = require_perm("stays.edit", "stays.mine", "stays.mine_res_edit")
EDIT_OR_MINE = require_perm("stays.edit", "stays.mine_res_edit")


@router.post("/reservations", response_model=PreviewedOut[ReservationDocOut])
def create_reservation(payload: ReservationIn, preview_flag: bool = PREVIEW,
                       principal: Principal = Depends(EDIT), db: Session = Depends(get_db)):
    return reservation_edit.create(db, principal, payload, preview_only=preview_flag, duty=TimesheetDuty(db))


@router.get("/reservations/{rid}", response_model=ReservationDocOut)
def get_reservation(rid: int, principal: Principal = Depends(READ_OR_MINE), db: Session = Depends(get_db)):
    return reservation_edit.get(db, principal, rid)


@router.put("/reservations/{rid}", response_model=PreviewedOut[ReservationDocOut])
def update_reservation(rid: int, payload: ReservationIn, preview_flag: bool = PREVIEW,
                       principal: Principal = Depends(EDIT_OR_MINE), db: Session = Depends(get_db)):
    return reservation_edit.update(db, principal, rid, payload, preview_only=preview_flag,
                                   duty=TimesheetDuty(db))


@router.post("/reservations/{rid}/status", response_model=PreviewedOut[ReservationDocOut])
def change_status(rid: int, payload: StatusIn, preview_flag: bool = PREVIEW,
                  principal: Principal = Depends(EDIT), db: Session = Depends(get_db)):
    return reservation_edit.change_status(db, principal, rid, payload, preview_only=preview_flag,
                                          duty=TimesheetDuty(db))


@router.get("/reservations/{rid}/cohabit", response_model=list[CohabitCandidateOut])
def cohabit(rid: int, principal: Principal = Depends(EDIT), db: Session = Depends(get_db)):
    return reservation_edit.cohabit(db, rid)


@router.post("/groups/join", response_model=PreviewedOut[GroupJoinedOut])
def join_group(payload: JoinIn, preview_flag: bool = PREVIEW, principal: Principal = Depends(EDIT),
               db: Session = Depends(get_db)):
    """Совместное проживание (§3.3): брони — в одну группу, с предпросмотром размещения."""
    return reservation_edit.join_group(db, principal, payload, preview_only=preview_flag,
                                       duty=TimesheetDuty(db))


@router.post("/groups/leave", response_model=PreviewedOut[ReservationDocOut])
def leave_group(payload: LeaveIn, preview_flag: bool = PREVIEW, principal: Principal = Depends(EDIT),
                db: Session = Depends(get_db)):
    return reservation_edit.leave_group(db, principal, payload, preview_only=preview_flag,
                                        duty=TimesheetDuty(db))


@router.post("/groups", response_model=StayGroupOut)
def create_group(payload: GroupIn, principal: Principal = Depends(EDIT), db: Session = Depends(get_db)):
    return reservation_edit.create_group(db, principal, payload)
