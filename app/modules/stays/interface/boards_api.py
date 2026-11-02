"""API шахматки батлеров и табло дня (§6.2, §6.3). Шахматка батлеров — только с фамилиями
(stays.view); табло — на всех уровнях, поля по уровню видимости (§8)."""
from __future__ import annotations

import datetime as dt
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.auth import Principal
from app.core.db import get_db
from app.core.permissions import require_perm

from ..adapters.duty_timesheet import TimesheetDuty
from ..adapters.orm import Guest
from ..application import boards, views
from ..application import mine as mine_app
from ..application.fund import FundError
from ..application.visibility import level_for
from .views_api import fund_filters

router = APIRouter(prefix="/api/stays", tags=["stays"])
MAX_DAYS = 62


@router.get("/board/butlers")
def board_butlers(first: dt.date, last: dt.date, principal: Principal = Depends(require_perm("stays.view")),
                  db: Session = Depends(get_db)):
    if last < first or (last - first).days + 1 > MAX_DAYS:
        raise HTTPException(status_code=422, detail=f"Период — не больше {MAX_DAYS} дней")
    return boards.butlers_board(db, first, last, TimesheetDuty(db))


@router.get("/day")
def day_board(date: dt.date, dims: dict = Depends(fund_filters), escorted_only: bool = False, special: bool = False,
              vip_code_ids: list[int] = Query(default=[]), employee_id: Optional[int] = None, q: str = "",
              principal: Principal = Depends(require_perm("stays.view", "stays.occupancy")),
              db: Session = Depends(get_db)):
    f = boards.DayFilters(**dims, escorted_only=escorted_only, special=special, vip_code_ids=tuple(vip_code_ids),
                          employee_id=employee_id, q=q)
    return boards.day_board(db, date, level_for(db, principal), f, TimesheetDuty(db))


@router.get("/occupancy")
def occupancy(first: dt.date, last: dt.date, dims: dict = Depends(fund_filters), escorted: bool = False,
              principal: Principal = Depends(require_perm("stays.view", "stays.occupancy")),
              db: Session = Depends(get_db)):
    try:
        return views.occupancy_grid(db, first, last, views.BoardFilters(**dims, escorted_only=escorted))
    except views.ViewError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e


def _me(principal: Principal) -> int:
    if principal.employee is None:
        raise HTTPException(status_code=404, detail="К учётной записи не привязан сотрудник")
    return principal.employee.id


@router.get("/mine/today")
def mine_today(principal: Principal = Depends(require_perm("stays.mine")), db: Session = Depends(get_db)):
    """«Мои гости» — «Сегодня» (часть 4 §5): брони, где батлер ведёт гостей в эту ночь."""
    return mine_app.mine_today(db, _me(principal))


@router.get("/mine/month")
def mine_month(first: dt.date, last: dt.date, principal: Principal = Depends(require_perm("stays.mine")),
               db: Session = Depends(get_db)):
    """«Мой месяц»: свои брони полосами, нагрузка по дням и отсутствия по Графику (не больше 62 дней)."""
    me = _me(principal)
    try:
        return mine_app.mine_month(db, me, first, last, TimesheetDuty(db))
    except FundError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e


@router.get("/mine/guests")
def mine_guests(q: str = "", offset: int = Query(0, ge=0),
                limit: int = Query(mine_app.GUESTS_PAGE, ge=1, le=mine_app.GUESTS_PAGE),
                principal: Principal = Depends(require_perm("stays.mine")), db: Session = Depends(get_db)):
    """«Все мои гости»: свои гости за всё время, поиск по ФИО (с полным уровнем — как подбор гостя),
    по 50."""
    return mine_app.mine_guests(db, _me(principal), q, offset, limit, full=level_for(db, principal) == "full")


@router.get("/mine/guests/{gid}")
def mine_guest_card(gid: int, principal: Principal = Depends(require_perm("stays.mine")),
                    db: Session = Depends(get_db)):
    """Карточка своего гостя: профиль целиком и история проживаний с тем, кто его вёл. Чужой — 403."""
    me = _me(principal)
    g = db.get(Guest, gid)
    if g is None:
        raise HTTPException(status_code=404, detail="Гость не найден")
    if not mine_app.owns_guest(db, me, gid):
        raise HTTPException(status_code=403, detail="Это не ваш гость: вы не ведёте его брони")
    return mine_app.mine_guest_card(db, me, g)
