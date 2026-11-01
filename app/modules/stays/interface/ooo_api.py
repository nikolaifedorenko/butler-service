"""API OOO (часть 2 §3.1, §6, §7): объект не в продаже по половинкам суток. Список видят все уровни
(персональных данных в OOO нет); запись — stays.edit, с предпросмотром через общий run_operation,
оптимистической версией (409) и журналом «было → стало»."""
from __future__ import annotations

import datetime as dt
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.audit import audit
from app.core.auth import Principal
from app.core.db import get_db
from app.core.permissions import require_perm

from ..adapters.orm import Ooo
from ..application import ooo, views
from ..application.fund import changes
from ..application.preview import change_window
from ._ops import PREVIEW, run
from .views_api import SEE, fund_filters

router = APIRouter(prefix="/api/stays", tags=["stays"])
EDIT = require_perm("stays.edit")


class OooIn(BaseModel):
    unit_id: int
    start: dt.date
    end: dt.date
    start_half: Literal["AM", "PM"] = "PM"          # «с» — с вечера дня выезда; «с утра» — AM
    end_half: Literal["AM", "PM"] = "AM"            # «по» — до утра дня заезда; «до вечера» — PM
    reason: str = Field("", max_length=120)


class OooPut(OooIn):
    version: int


def _query(first: Optional[dt.date] = None, last: Optional[dt.date] = None, dims: dict = Depends(fund_filters),
           q: str = "", sort: str = "start", dir: Literal["asc", "desc"] = "asc", offset: int = Query(0, ge=0),
           limit: int = Query(ooo.MAX_LIMIT, ge=1, le=ooo.MAX_LIMIT)) -> ooo.OooQuery:
    try:
        return ooo.OooQuery(first, last, views.BoardFilters(**dims, q=q), sort, dir, offset, limit)
    except views.ViewError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e


def _found(db: Session, oid: int) -> Ooo:
    o = db.get(Ooo, oid)
    if o is None:
        raise HTTPException(status_code=404, detail="OOO не найден")
    return o


def _op(db: Session, principal: Principal, payload: Optional[OooIn], oid: Optional[int], version: Optional[int] = None):
    def op():
        if payload is None:
            before = ooo.delete_ooo(db, oid, version)
            audit(db, principal, "stays_ooo", f"ooo:{oid}", {"diff": changes(before, {k: None for k in before})})
            return {"id": oid, "deleted": True}
        o, before = ooo.save_ooo(db, payload.model_dump(), oid, principal.user.id)
        after = ooo.ooo_dict(o)
        audit(db, principal, "stays_ooo", f"ooo:{o.id}", {"diff": changes(before, after)})
        return after
    return op


@router.get("/ooo")
def ooo_list(query: ooo.OooQuery = Depends(_query), principal: Principal = Depends(SEE),
             db: Session = Depends(get_db)):
    return ooo.list_ooo(db, query)


@router.post("/ooo")
def create_ooo(payload: OooIn, preview_flag: bool = PREVIEW, principal: Principal = Depends(EDIT),
               db: Session = Depends(get_db)):
    return run(db, _op(db, principal, payload, None), preview_flag, change_window((payload.start, payload.end)),
               principal)


@router.put("/ooo/{oid}")
def update_ooo(oid: int, payload: OooPut, preview_flag: bool = PREVIEW, principal: Principal = Depends(EDIT),
               db: Session = Depends(get_db)):
    o = _found(db, oid)
    window = change_window((payload.start, payload.end), (o.start, o.end))
    return run(db, _op(db, principal, payload, oid), preview_flag, window, principal)


@router.delete("/ooo/{oid}")
def remove_ooo(oid: int, version: int, preview_flag: bool = PREVIEW, principal: Principal = Depends(EDIT),
               db: Session = Depends(get_db)):
    o = _found(db, oid)
    return run(db, _op(db, principal, None, oid, version), preview_flag, change_window((o.start, o.end)), principal)
