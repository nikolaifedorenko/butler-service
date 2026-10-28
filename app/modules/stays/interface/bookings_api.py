"""Вкладка «Брони» (спецификация фонда по версиям §8): список бронирований и его выгрузка в Excel.
Только уровни «с фамилиями» и «полный»: список без фамилий бесполезен и сам по себе оракул."""
from __future__ import annotations

import datetime as dt
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.core.audit import audit
from app.core.auth import Principal
from app.core.db import get_db
from app.core.permissions import require_perm

from ..application import bookings, views
from ..application.export import bookings_xlsx
from ..application.visibility import level_for
from .export_api import XLSX
from .views_api import fund_filters

router = APIRouter(prefix="/api/stays", tags=["stays"])


def _query(first: dt.date, last: dt.date, mode: Literal["stay", "check_in", "check_out", "created"] = "stay",
           dims: dict = Depends(fund_filters), escorted: bool = False, vip: bool = False,
           employee_id: Optional[int] = None, q: str = "", statuses: list[str] = Query(default=[]),
           label_ids: list[int] = Query(default=[]), unassigned: bool = False, with_warnings: bool = False,
           sort: str = "check_in", dir: Literal["asc", "desc"] = "asc", offset: int = Query(0, ge=0),
           limit: int = Query(bookings.MAX_LIMIT, ge=1, le=bookings.MAX_LIMIT)) -> bookings.BookingQuery:
    try:
        return bookings.BookingQuery(
            first, last, mode, views.BoardFilters(**dims, escorted_only=escorted, vip=vip, employee_id=employee_id, q=q),
            tuple(statuses), tuple(label_ids), unassigned, with_warnings, sort, dir, offset, limit)
    except views.ViewError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e


def _access(db: Session, principal: Principal) -> tuple[str, bool]:
    level = level_for(db, principal)
    if level is None or level == "occupancy":
        raise HTTPException(status_code=403, detail="Список броней доступен с правом «Шахматки с фамилиями»")
    # права уже вычислил гейт require_perm этого запроса — повторно не запрашиваем
    return level, "stays.guests" in principal.gate_permissions


@router.get("/bookings")
def bookings_list(query: bookings.BookingQuery = Depends(_query),
                  principal: Principal = Depends(require_perm("stays.view")), db: Session = Depends(get_db)):
    level, can_guests = _access(db, principal)
    return bookings.list_bookings(db, query, level, can_guests)


@router.get("/bookings/export")
def bookings_export(query: bookings.BookingQuery = Depends(_query),
                    principal: Principal = Depends(require_perm("stays.export")), db: Session = Depends(get_db)):
    level, can_guests = _access(db, principal)
    rows = bookings.find_bookings(db, query, level, can_guests)
    f = query.filters
    audit(db, principal, "stays_export", "export:bookings", {
        "kind": "bookings", "first": query.first.isoformat(), "last": query.last.isoformat(), "mode": query.mode,
        "sort": query.sort, "dir": query.dir, "rows": len(rows), "statuses": list(query.statuses),
        "label_ids": list(query.label_ids), "unassigned": query.unassigned, "with_warnings": query.with_warnings,
        "group_ids": list(f.group_ids), "category_ids": list(f.category_ids), "flag_ids": list(f.flag_ids),
        "kinds": list(f.kinds), "floor": f.floor, "escorted": f.escorted_only, "vip": f.vip,
        "employee_id": f.employee_id, "q": f.q})
    db.commit()
    name = f"bookings_{query.first.isoformat()}_{query.last.isoformat()}.xlsx"
    return Response(bookings_xlsx(rows), media_type=XLSX,
                    headers={"Content-Disposition": f'attachment; filename="{name}"'})
