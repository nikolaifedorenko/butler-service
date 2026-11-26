"""API шахматки батлеров и табло дня (§6.2, §6.3). Шахматка батлеров — только с фамилиями
(stays.view); табло — на всех уровнях, поля по уровню видимости (§8). «Мои гости» — батлеру
(stays.mine).

Правила — в прикладном слое: ``board_screen`` и ``mine_screen``. Роутер разбирает запрос и
проверяет право.
"""
from __future__ import annotations

import datetime as dt
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.auth import Principal
from app.core.db import get_db
from app.core.permissions import require_perm
from app.core.time import local_date
from app.modules.stays.application import guest_events
from app.modules.stays.application import mine as mine_app
from app.modules.stays.application.duty import timesheet_duty

from ..application import board_screen, boards, mine_screen, views
from .schemas import (
    ButlersBoardOut,
    DayBoardOut,
    GuestEventsOut,
    MineGuestCardOut,
    MineGuestsOut,
    MineMonthOut,
    MineTodayOut,
    OccupancyOut,
)
from .views_api import fund_filters

router = APIRouter(prefix="/api/stays", tags=["stays"])


@router.get("/board/butlers", response_model=ButlersBoardOut)
def board_butlers(first: dt.date, last: dt.date, principal: Principal = Depends(require_perm("stays.view")),
                  db: Session = Depends(get_db)):
    return board_screen.butlers_board(db, first, last, timesheet_duty(db))


@router.get("/day", response_model=DayBoardOut)
def day_board(date: Optional[dt.date] = None, dims: dict = Depends(fund_filters), escorted_only: bool = False, special: bool = False,
              vip_code_ids: list[int] = Query(default=[]), employee_id: Optional[int] = None, q: str = "",
              principal: Principal = Depends(require_perm("stays.view", "stays.occupancy")),
              db: Session = Depends(get_db)):
    f = boards.DayFilters(**dims, escorted_only=escorted_only, special=special, vip_code_ids=tuple(vip_code_ids),
                          employee_id=employee_id, q=q)
    return board_screen.day_board(db, principal, date or local_date(), f, timesheet_duty(db))


@router.get("/occupancy", response_model=OccupancyOut)
def occupancy(first: dt.date, last: dt.date, dims: dict = Depends(fund_filters), escorted: bool = False,
              principal: Principal = Depends(require_perm("stays.view", "stays.occupancy")),
              db: Session = Depends(get_db)):
    return board_screen.occupancy(db, first, last, views.BoardFilters(**dims, escorted_only=escorted))


@router.get("/mine/today", response_model=MineTodayOut)
def mine_today(principal: Principal = Depends(require_perm("stays.mine")), db: Session = Depends(get_db)):
    """«Мои гости» — «Сегодня» (часть 4 §5): брони, где батлер ведёт гостей в эту ночь."""
    return mine_screen.today_reservations(db, principal)


@router.get("/mine/month", response_model=MineMonthOut)
def mine_month(first: dt.date, last: dt.date, principal: Principal = Depends(require_perm("stays.mine")),
               db: Session = Depends(get_db)):
    """«Мой месяц»: свои брони полосами, нагрузка по дням и отсутствия по Графику (не больше 62 дней)."""
    return mine_screen.month(db, principal, first, last, timesheet_duty(db))


@router.get("/mine/guests", response_model=MineGuestsOut)
def mine_guests(q: str = "", offset: int = Query(0, ge=0),
                limit: int = Query(mine_app.GUESTS_PAGE, ge=1, le=mine_app.GUESTS_PAGE),
                principal: Principal = Depends(require_perm("stays.mine")), db: Session = Depends(get_db)):
    """«Все мои гости»: свои гости за всё время, поиск по ФИО, по 50."""
    return mine_screen.guests(db, principal, q, offset, limit)


@router.get("/mine/guests/{gid}", response_model=MineGuestCardOut)
def mine_guest_card(gid: int, principal: Principal = Depends(require_perm("stays.mine")),
                    db: Session = Depends(get_db)):
    """Карточка своего гостя: профиль целиком и история проживаний с тем, кто его вёл. Чужой — 403."""
    return mine_screen.guest_card(db, principal, gid)


@router.get("/guest-events", response_model=GuestEventsOut)
def events_calendar(month: dt.date | None = None, kind: guest_events.EventKind | None = None,
                    confirmed_only: bool = False, vip_code_ids: list[int] = Query(default=[]), special: bool = False,
                    principal: Principal = Depends(require_perm("stays.guests", "stays.mine")),
                    db: Session = Depends(get_db)):
    """Месяц событий доступных гостей и их проживание на дату события."""
    return guest_events.calendar(db, principal, month, kind=kind, confirmed_only=confirmed_only,
                                 vip_code_ids=vip_code_ids, special=special)
