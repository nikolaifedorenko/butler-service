"""API журнала аудита. Правила — в ``application/journal.py``."""
from __future__ import annotations

import datetime as dt
from typing import Optional

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.core.auth import Principal
from app.core.db import get_db
from app.core.permissions import require_perm
from app.core.schemas import ApiModel
from app.modules.exchange.application.tables import CSV_MEDIA_TYPE, attachment

from ..application import journal

router = APIRouter(prefix="/api/audit", tags=["audit"])
VIEW = require_perm("audit.view")


class AuditItemOut(ApiModel):
    id: int
    ts: Optional[str]           # местное время объекта
    actor: str
    action: str
    action_title: str
    target: str
    payload: str                # данные записи — JSON строкой


class AuditActionOut(ApiModel):
    action: str
    title: str


class AuditPageOut(ApiModel):
    total: int
    items: list[AuditItemOut]
    actions: list[AuditActionOut]


@router.get("", response_model=AuditPageOut)
def list_audit(q: str = "", action: str = "", actor: str = "", date_from: Optional[dt.date] = None,
               date_to: Optional[dt.date] = None, limit: int = 100, offset: int = 0,
               principal: Principal = Depends(VIEW), db: Session = Depends(get_db)):
    return journal.page(db, q=q, action=action, actor=actor, date_from=date_from, date_to=date_to,
                        limit=limit, offset=offset)


@router.get("/csv", response_class=Response)
def export_csv(q: str = "", action: str = "", actor: str = "", date_from: Optional[dt.date] = None,
               date_to: Optional[dt.date] = None, principal: Principal = Depends(VIEW),
               db: Session = Depends(get_db)):
    data = journal.export_csv(db, q=q, action=action, actor=actor, date_from=date_from, date_to=date_to)
    return Response(content=data, media_type=CSV_MEDIA_TYPE, headers=attachment("audit.csv"))
