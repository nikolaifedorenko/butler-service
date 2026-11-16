"""API вкладки «Управленческий табель» (16.6): просмотр, закрытие и пересчёт периода, выгрузка.

Правила — в ``application/mgmt_screen.py``; роутер разбирает запрос и проверяет право.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.core.auth import Principal
from app.core.db import get_db
from app.core.permissions import require_perm
from app.modules.exchange.application.tables import XLSX_MEDIA_TYPE, attachment

from ..application import mgmt_screen
from ..application.mgmt_screen import PeriodAction
from .schemas import MgmtOut, PeriodActionOut

router = APIRouter(prefix="/api/mgmt", tags=["mgmt-timesheet"])


@router.get("", response_model=MgmtOut)
def get_mgmt(year: int, month: int, half: Optional[int] = None, employee_id: Optional[int] = None,
             detail: bool = False, principal: Principal = Depends(require_perm("mgmt.view")),
             db: Session = Depends(get_db)):
    """Управленческий табель периода: месяц либо половина месяца."""
    return mgmt_screen.table(db, principal, year, month, half, employee_id, detail)


@router.post("/close", response_model=PeriodActionOut)
def close(payload: PeriodAction, principal: Principal = Depends(require_perm("mgmt.close")),
          db: Session = Depends(get_db)):
    """Закрыть период у всего штата: сначала предпроверка каждого, затем запись."""
    return mgmt_screen.close(db, principal, payload)


@router.post("/recalculate", response_model=PeriodActionOut)
def recalc(payload: PeriodAction, principal: Principal = Depends(require_perm("mgmt.recalculate")),
           db: Session = Depends(get_db)):
    """Пересчитать последний закрытый период у всего штата."""
    return mgmt_screen.recalc(db, principal, payload)


@router.get("/xlsx", response_class=Response)
def export_xlsx(year: int, month: int, half: Optional[int] = None,
                principal: Principal = Depends(require_perm("mgmt.view")),
                db: Session = Depends(get_db)):
    """Управленческий табель в Excel."""
    content, filename = mgmt_screen.export_xlsx(db, principal, year, month, half)
    return Response(content=content, media_type=XLSX_MEDIA_TYPE, headers=attachment(filename))
