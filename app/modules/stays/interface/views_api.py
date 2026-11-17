"""API видов «Шахматки» (§6): шахматка объектов, карточки брони и гостя, лента изменений.
Уровень видимости персональных данных определяется правами (§8).

Правила — в прикладном слое: ``application/view_screen.py``. Роутер разбирает запрос и проверяет право.
"""
from __future__ import annotations

import datetime as dt
from typing import Optional

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.core.auth import Principal
from app.core.db import get_db
from app.core.errors import Validation
from app.core.permissions import require_perm

from ..adapters.duty_timesheet import TimesheetDuty
from ..application import view_screen, views
from .schemas import GuestFullCardOut, ReservationCardOut, ReservationHistoryOut, UnitsBoardOut

router = APIRouter(prefix="/api/stays", tags=["stays"])
SEE = require_perm("stays.view", "stays.occupancy")


REMOVED_PARAMS = ("building", "category_id", "kind", "kinds", "vip")


def fund_filters(request: Request, group_ids: list[int] = Query(default=[]),
                 category_ids: list[int] = Query(default=[]), flag_ids: list[int] = Query(default=[]),
                 kind_ids: list[int] = Query(default=[]), floor: Optional[str] = None) -> dict:
    """Измерения фонда (§7) — повторяющиеся параметры. Прежние одиночные параметры — 422, а не
    молча без фильтра: старый клиент иначе показал бы весь фонд как отфильтрованный."""
    old = [p for p in REMOVED_PARAMS if p in request.query_params]
    if old:
        raise Validation(f"Параметр {', '.join(old)} больше не поддерживается: "
                         "group_ids, category_ids, flag_ids, kind_ids, special, vip_code_ids")
    return {"group_ids": tuple(group_ids), "category_ids": tuple(category_ids), "flag_ids": tuple(flag_ids),
            "kind_ids": tuple(kind_ids), "floor": floor or None}


@router.get("/board/units", response_model=UnitsBoardOut)
def board_units(first: dt.date, last: dt.date, dims: dict = Depends(fund_filters), escorted: bool = False,
                special: bool = False, vip_code_ids: list[int] = Query(default=[]), employee_id: Optional[int] = None,
                q: str = "", principal: Principal = Depends(SEE), db: Session = Depends(get_db)):
    f = views.BoardFilters(**dims, escorted_only=escorted, special=special, vip_code_ids=tuple(vip_code_ids),
                           employee_id=employee_id, q=q)
    return view_screen.units_board(db, principal, first, last, f)


@router.get("/reservations/{rid}/card", response_model=ReservationCardOut)
def reservation_card(rid: int, principal: Principal = Depends(require_perm("stays.view")),
                     db: Session = Depends(get_db)):
    return view_screen.reservation_card(db, principal, rid, TimesheetDuty(db))


@router.get("/reservations/{rid}/history", response_model=list[ReservationHistoryOut])
def reservation_history(rid: int, principal: Principal = Depends(require_perm("stays.view")),
                        db: Session = Depends(get_db)):
    return view_screen.reservation_history(db, principal, rid)


@router.get("/guests/{gid}/card", response_model=GuestFullCardOut)
def guest_card(gid: int, principal: Principal = Depends(require_perm("stays.guests", "stays.mine")),
               db: Session = Depends(get_db)):
    """Карточка гостя целиком (с историей проживаний): stays.guests — любого, stays.mine — своего."""
    return view_screen.guest_card(db, principal, gid)
