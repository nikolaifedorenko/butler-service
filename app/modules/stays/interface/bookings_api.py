"""Вкладка «Брони» (спецификация фонда по версиям §8): список бронирований и его выгрузка в Excel.
Только уровни «с фамилиями» и «полный»: список без фамилий бесполезен и сам по себе оракул.

Правила — в прикладном слое: ``application/booking_screen.py``. Роутер разбирает фильтры запроса
и проверяет право эндпоинта.
"""
from __future__ import annotations

import datetime as dt
from typing import Literal, Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.core.auth import Principal
from app.core.db import get_db
from app.core.permissions import require_perm

from ..application import booking_screen, bookings, views
from .export_api import XLSX
from .schemas import BookingListOut
from .views_api import fund_filters

router = APIRouter(prefix="/api/stays", tags=["stays"])


def _query(first: dt.date, last: dt.date, mode: Literal["stay", "check_in", "check_out", "created"] = "stay",
           dims: dict = Depends(fund_filters), escorted: bool = False, special: bool = False,
           vip_code_ids: list[int] = Query(default=[]), employee_id: Optional[int] = None, q: str = "",
           statuses: list[str] = Query(default=[]),
           label_ids: list[int] = Query(default=[]), unassigned: bool = False, with_warnings: bool = False,
           sort: str = "check_in", dir: Literal["asc", "desc"] = "asc", offset: int = Query(0, ge=0),
           limit: int = Query(bookings.MAX_LIMIT, ge=1, le=bookings.MAX_LIMIT)) -> bookings.BookingQuery:
    return bookings.BookingQuery(
        first, last, mode, views.BoardFilters(**dims, escorted_only=escorted, special=special,
                                              vip_code_ids=tuple(vip_code_ids), employee_id=employee_id, q=q),
        tuple(statuses), tuple(label_ids), unassigned, with_warnings, sort, dir, offset, limit)


@router.get("/bookings", response_model=BookingListOut)
def bookings_list(query: bookings.BookingQuery = Depends(_query),
                  principal: Principal = Depends(require_perm("stays.view")), db: Session = Depends(get_db)):
    return booking_screen.list_bookings(db, principal, query)


@router.get("/bookings/export", response_class=Response, responses={200: {"content": {XLSX: {}}}})
def bookings_export(query: bookings.BookingQuery = Depends(_query),
                    principal: Principal = Depends(require_perm("stays.export")), db: Session = Depends(get_db)):
    content, filename = booking_screen.export(db, principal, query)
    return Response(content, media_type=XLSX, headers={"Content-Disposition": f'attachment; filename="{filename}"'})
