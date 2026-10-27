"""API шахматки батлеров и табло дня (§6.2, §6.3). Шахматка батлеров — только с фамилиями
(stays.view); табло — на всех уровнях, поля по уровню видимости (§8)."""
from __future__ import annotations

import datetime as dt
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.auth import Principal
from app.core.db import get_db
from app.core.permissions import require_perm

from ..adapters.duty_timesheet import TimesheetDuty
from ..application import boards, views
from ..application.mine import my_guests
from ..application.visibility import level_for

router = APIRouter(prefix="/api/stays", tags=["stays"])
MAX_DAYS = 62


@router.get("/board/butlers")
def board_butlers(first: dt.date, last: dt.date, principal: Principal = Depends(require_perm("stays.view")),
                  db: Session = Depends(get_db)):
    if last < first or (last - first).days + 1 > MAX_DAYS:
        raise HTTPException(status_code=422, detail=f"Период — не больше {MAX_DAYS} дней")
    return boards.butlers_board(db, first, last, TimesheetDuty(db))


@router.get("/day")
def day_board(date: dt.date, escorted_only: bool = False, vip: bool = False, employee_id: Optional[int] = None,
              q: str = "", principal: Principal = Depends(require_perm("stays.view", "stays.occupancy")),
              db: Session = Depends(get_db)):
    return boards.day_board(db, date, level_for(db, principal),
                            boards.DayFilters(escorted_only, vip, employee_id, q), TimesheetDuty(db))


@router.get("/occupancy")
def occupancy(first: dt.date, last: dt.date, group_id: Optional[int] = None,
              principal: Principal = Depends(require_perm("stays.view", "stays.occupancy")),
              db: Session = Depends(get_db)):
    try:
        return views.occupancy_grid(db, first, last, group_id)
    except views.ViewError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e


@router.get("/mine")
def mine(principal: Principal = Depends(require_perm("stays.mine")), db: Session = Depends(get_db)):
    """«Мои гости» (§6.6): брони, где батлер ведёт гостей сегодня и неделю вперёд, и вчерашние."""
    if principal.employee is None:
        raise HTTPException(status_code=404, detail="К учётной записи не привязан сотрудник")
    return my_guests(db, principal.employee.id)
