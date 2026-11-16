"""Журнал аудита: кто, когда и что менял — поиск, фильтры, выгрузка."""
from __future__ import annotations

import datetime as dt
import json
from typing import Optional

from sqlalchemy import Select, Text, cast, func, or_, select
from sqlalchemy.orm import Session

from app.core.audit import AuditLog
from app.core.manifest import audit_titles
from app.core.time import local_iso, local_midnight
from app.modules.exchange.application.tables import write_csv

CSV_HEADER = ["Время", "Кто", "Действие", "Объект", "Данные"]


def _query(q: str, action: str, actor: str, date_from: Optional[dt.date], date_to: Optional[dt.date]) -> Select:
    """Записи по фильтрам; даты — местные сутки объекта."""
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
        stmt = stmt.where(AuditLog.ts >= local_midnight(date_from))
    if date_to:
        stmt = stmt.where(AuditLog.ts < local_midnight(date_to + dt.timedelta(days=1)))
    return stmt


def _item(row: AuditLog, titles: dict[str, str]) -> dict:
    return {"id": row.id, "ts": local_iso(row.ts), "actor": row.actor_name, "action": row.action,
            "action_title": titles.get(row.action, row.action), "target": row.target,
            "payload": json.dumps(row.payload, ensure_ascii=False)}


def page(db: Session, *, q: str = "", action: str = "", actor: str = "", date_from: Optional[dt.date] = None,
         date_to: Optional[dt.date] = None, limit: int = 100, offset: int = 0) -> dict:
    """Страница журнала, новые записи первыми; actions — действия, которые в журнале встречались."""
    stmt = _query(q, action, actor, date_from, date_to)
    titles = audit_titles()
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = db.scalars(stmt.order_by(AuditLog.ts.desc(), AuditLog.id.desc())
                      .limit(max(1, min(limit, 500))).offset(max(0, offset))).all()
    actions = sorted(db.scalars(select(AuditLog.action).distinct()))
    return {"total": total, "items": [_item(r, titles) for r in rows],
            "actions": [{"action": a, "title": titles.get(a, a)} for a in actions]}


def export_csv(db: Session, *, q: str = "", action: str = "", actor: str = "",
               date_from: Optional[dt.date] = None, date_to: Optional[dt.date] = None) -> bytes:
    """Журнал по фильтрам в CSV, не больше 20 000 записей."""
    titles = audit_titles()
    rows = db.scalars(_query(q, action, actor, date_from, date_to).order_by(AuditLog.ts.desc()).limit(20000))
    items = (_item(r, titles) for r in rows)
    return write_csv(CSV_HEADER, ([i["ts"], i["actor"], i["action_title"], i["target"], i["payload"]] for i in items))
