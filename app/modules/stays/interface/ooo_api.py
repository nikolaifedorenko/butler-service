"""API OOO (часть 2 §3.1, §6, §7): объект не в продаже по половинкам суток. Список видят все уровни
(персональных данных в OOO нет); запись — stays.edit, с предпросмотром, оптимистической версией (409)
и журналом «было → стало».

Правила — в прикладном слое: ``application/ooo_edit.py``. Роутер разбирает запрос и проверяет право.
"""
from __future__ import annotations

import datetime as dt
from typing import Literal, Optional

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.core.auth import Principal
from app.core.db import get_db
from app.core.permissions import require_perm

from ..adapters.duty_timesheet import TimesheetDuty
from ..application import ooo, ooo_edit
from ..application.ooo_edit import OooIn, OooPut
from ..application.view_filters import BoardFilters, fund_filter_dims
from ._ops import PREVIEW
from .schemas import DeletedOut, OooListOut, OooSavedOut, PreviewedOut

router = APIRouter(prefix="/api/stays", tags=["stays"])
EDIT = require_perm("stays.edit")
SEE = require_perm("stays.view", "stays.occupancy")


def fund_filters(request: Request, group_ids: list[int] = Query(default=[]),
                 category_ids: list[int] = Query(default=[]), flag_ids: list[int] = Query(default=[]),
                 kind_ids: list[int] = Query(default=[]), floor: Optional[str] = None) -> dict:
    """Измерения фонда (§7) — повторяющиеся параметры; прежние одиночные — 422."""
    return fund_filter_dims(request.query_params, group_ids, category_ids, flag_ids, kind_ids, floor)


def _query(first: Optional[dt.date] = None, last: Optional[dt.date] = None, dims: dict = Depends(fund_filters),
           q: str = "", sort: str = "start", dir: Literal["asc", "desc"] = "asc", offset: int = Query(0, ge=0),
           limit: int = Query(ooo.MAX_LIMIT, ge=1, le=ooo.MAX_LIMIT)) -> ooo.OooQuery:
    return ooo.OooQuery(first, last, BoardFilters(**dims, q=q), sort, dir, offset, limit)


@router.get("/ooo", response_model=OooListOut)
def ooo_list(query: ooo.OooQuery = Depends(_query), principal: Principal = Depends(SEE),
             db: Session = Depends(get_db)):
    return ooo.list_ooo(db, query)


@router.post("/ooo", response_model=PreviewedOut[OooSavedOut])
def create_ooo(payload: OooIn, preview_flag: bool = PREVIEW, principal: Principal = Depends(EDIT),
               db: Session = Depends(get_db)):
    return ooo_edit.save(db, principal, payload, None, preview_only=preview_flag, duty=TimesheetDuty(db))


@router.put("/ooo/{oid}", response_model=PreviewedOut[OooSavedOut])
def update_ooo(oid: int, payload: OooPut, preview_flag: bool = PREVIEW, principal: Principal = Depends(EDIT),
               db: Session = Depends(get_db)):
    return ooo_edit.save(db, principal, payload, oid, preview_only=preview_flag, duty=TimesheetDuty(db))


@router.delete("/ooo/{oid}", response_model=PreviewedOut[DeletedOut])
def remove_ooo(oid: int, version: int, preview_flag: bool = PREVIEW, principal: Principal = Depends(EDIT),
               db: Session = Depends(get_db)):
    return ooo_edit.remove(db, principal, oid, version, preview_only=preview_flag, duty=TimesheetDuty(db))
