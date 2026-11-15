"""Журнал аудита: кто, когда и что менял — с фильтрами и постраничной выдачей."""
from __future__ import annotations

import datetime as dt
import json
from typing import Optional

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlalchemy import Text, cast, func, or_, select
from sqlalchemy.orm import Session

from app.core.audit import AuditLog
from app.core.auth import Principal
from app.core.db import get_db
from app.core.manifest import audit_titles
from app.core.permissions import require_perm
from app.core.time import local_iso, local_midnight
from app.modules.exchange.application.tables import CSV_MEDIA_TYPE, attachment, write_csv

router = APIRouter(prefix="/api/audit", tags=["audit"])

def _titles() -> dict[str, str]:
    """Названия действий журнала — из манифестов модулей (ADR-0012)."""
    return audit_titles()


def _utc_bound(d: dt.date) -> dt.datetime:
    """Начало суток объекта как момент: фильтр журнала задаётся местными датами."""
    return local_midnight(d)


def _query(q, action, actor, date_from, date_to):
    stmt = select(AuditLog)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(AuditLog.target.ilike(like), cast(AuditLog.payload, Text).ilike(like),
                              AuditLog.actor_name.ilike(like), AuditLog.action.ilike(like)))
    if action:
        stmt = stmt.where(AuditLog.action == action)
    if actor:
        stmt = stmt.where(AuditLog.actor_name.ilike(f"%{actor}%"))
    if date_from:
        stmt = stmt.where(AuditLog.ts >= _utc_bound(date_from))
    if date_to:
        stmt = stmt.where(AuditLog.ts < _utc_bound(date_to + dt.timedelta(days=1)))
    return stmt


def _item(r: AuditLog) -> dict:
    return {"id": r.id, "ts": local_iso(r.ts), "actor": r.actor_name,
            "action": r.action, "action_title": _titles().get(r.action, r.action),
            "target": r.target, "payload": json.dumps(r.payload, ensure_ascii=False)}


@router.get("")
def list_audit(q: str = "", action: str = "", actor: str = "", date_from: Optional[dt.date] = None,
               date_to: Optional[dt.date] = None, limit: int = 100, offset: int = 0,
               principal: Principal = Depends(require_perm("audit.view")), db: Session = Depends(get_db)):
    stmt = _query(q, action, actor, date_from, date_to)
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = db.scalars(stmt.order_by(AuditLog.ts.desc(), AuditLog.id.desc())
                      .limit(max(1, min(limit, 500))).offset(max(0, offset))).all()
    actions = sorted(db.scalars(select(AuditLog.action).distinct()))
    return {"total": total, "items": [_item(r) for r in rows],
            "actions": [{"action": a, "title": _titles().get(a, a)} for a in actions]}


@router.get("/csv")
def export_csv(q: str = "", action: str = "", actor: str = "", date_from: Optional[dt.date] = None,
               date_to: Optional[dt.date] = None, principal: Principal = Depends(require_perm("audit.view")),
               db: Session = Depends(get_db)):
    rows = db.scalars(_query(q, action, actor, date_from, date_to).order_by(AuditLog.ts.desc()).limit(20000))
    items = (_item(r) for r in rows)
    data = write_csv(["Время", "Кто", "Действие", "Объект", "Данные"],
                     ([i["ts"], i["actor"], i["action_title"], i["target"], i["payload"]] for i in items))
    return Response(content=data, media_type=CSV_MEDIA_TYPE, headers=attachment("audit.csv"))
