"""API видов «Шахматки» (§6): шахматка объектов, карточки брони и гостя, лента изменений.
Уровень видимости персональных данных определяется правами (§8)."""
from __future__ import annotations

import datetime as dt
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from app.core.auth import Principal
from app.core.db import get_db
from app.core.permissions import require_perm

from ..adapters.duty_timesheet import TimesheetDuty
from ..adapters.orm import Guest
from ..application import guests, history, views
from ..application.visibility import level_for

router = APIRouter(prefix="/api/stays", tags=["stays"])
SEE = require_perm("stays.view", "stays.occupancy")


REMOVED_PARAMS = ("building", "category_id", "kind", "kinds")


def fund_filters(request: Request, group_ids: list[int] = Query(default=[]),
                 category_ids: list[int] = Query(default=[]), flag_ids: list[int] = Query(default=[]),
                 kind_ids: list[int] = Query(default=[]), floor: Optional[str] = None) -> dict:
    """Измерения фонда (§7) — повторяющиеся параметры. Прежние одиночные параметры — 422, а не
    молча без фильтра: старый клиент иначе показал бы весь фонд как отфильтрованный."""
    old = [p for p in REMOVED_PARAMS if p in request.query_params]
    if old:
        raise HTTPException(status_code=422, detail=f"Параметр {', '.join(old)} больше не поддерживается: "
                                                    "group_ids, category_ids, flag_ids, kind_ids")
    return {"group_ids": tuple(group_ids), "category_ids": tuple(category_ids), "flag_ids": tuple(flag_ids),
            "kind_ids": tuple(kind_ids), "floor": floor or None}


@router.get("/board/units")
def board_units(first: dt.date, last: dt.date, dims: dict = Depends(fund_filters), escorted: bool = False,
                vip: bool = False, employee_id: Optional[int] = None, q: str = "",
                principal: Principal = Depends(SEE), db: Session = Depends(get_db)):
    level = level_for(db, principal)
    f = views.BoardFilters(**dims, escorted_only=escorted, vip=vip, employee_id=employee_id, q=q)
    try:
        return views.units_board(db, first, last, f, level)
    except views.ViewError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e


@router.get("/reservations/{rid}/card")
def reservation_card(rid: int, principal: Principal = Depends(require_perm("stays.view")),
                     db: Session = Depends(get_db)):
    try:
        return views.reservation_card(db, rid, level_for(db, principal), TimesheetDuty(db))
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.get("/reservations/{rid}/history")
def reservation_history(rid: int, principal: Principal = Depends(require_perm("stays.view")),
                        db: Session = Depends(get_db)):
    return history.reservation_history(db, rid, level_for(db, principal))


@router.get("/guests/{gid}/card")
def guest_card(gid: int, principal: Principal = Depends(require_perm("stays.guests")),
               db: Session = Depends(get_db)):
    g = db.get(Guest, gid)
    if g is None:
        raise HTTPException(status_code=404, detail="Гость не найден")
    return {**guests.guest_dict(g), "links": guests.links_of(db, gid), "stays": history.guest_stays(db, gid)}
