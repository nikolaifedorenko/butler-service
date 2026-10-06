"""Журнал аудита: кто, когда и что менял — с фильтрами и постраничной выдачей."""
from __future__ import annotations

import csv
import datetime as dt
import io
from typing import Optional

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..auth import Principal
from ..db import get_db
from ..deps import utc_to_local
from ..models import AuditLog
from ..permissions import require_perm

router = APIRouter(prefix="/api/audit", tags=["audit"])

ACTION_TITLES = {
    "login": "Вход", "logout": "Выход", "punch_in": "Отметка «Пришёл»", "punch_out": "Отметка «Ушёл»",
    "punch_in_backfill": "Приход задним числом", "punch_out_backfill": "Уход задним числом",
    "punch_delete": "Отмена отметки", "punch_note": "Описание переработки",
    "tabel_cell": "Табель: ячейка", "tabel_fill_from_schedule": "Табель: заполнение из Графика",
    "period_close": "УТ: закрытие периода", "period_recalculate": "УТ: пересчёт периода",
    "engine_settings": "Настройки движка", "day_modifier_create": "Модификатор дня: добавлен",
    "day_modifier_delete": "Модификатор дня: удалён",
    "access_role": "Права роли", "access_group_create": "Группа доступа: создана",
    "access_group_update": "Группа доступа: изменена", "access_group_delete": "Группа доступа: удалена",
    "access_group_grants": "Права группы", "access_group_members": "Состав группы",
    "access_user_grants": "Индивидуальные права",
}


def _query(q, action, actor, date_from, date_to):
    stmt = select(AuditLog)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(AuditLog.target.ilike(like), AuditLog.payload_json.ilike(like),
                              AuditLog.actor_name.ilike(like), AuditLog.action.ilike(like)))
    if action:
        stmt = stmt.where(AuditLog.action == action)
    if actor:
        stmt = stmt.where(AuditLog.actor_name.ilike(f"%{actor}%"))
    if date_from:
        stmt = stmt.where(AuditLog.ts >= dt.datetime.combine(date_from, dt.time(0)) - dt.timedelta(hours=3))
    if date_to:
        stmt = stmt.where(AuditLog.ts < dt.datetime.combine(date_to + dt.timedelta(days=1), dt.time(0)))
    return stmt


def _item(r: AuditLog) -> dict:
    return {"id": r.id, "ts": utc_to_local(r.ts).isoformat(timespec="seconds"), "actor": r.actor_name,
            "action": r.action, "action_title": ACTION_TITLES.get(r.action, r.action),
            "target": r.target, "payload": r.payload_json}


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
            "actions": [{"action": a, "title": ACTION_TITLES.get(a, a)} for a in actions]}


@router.get("/csv")
def export_csv(q: str = "", action: str = "", actor: str = "", date_from: Optional[dt.date] = None,
               date_to: Optional[dt.date] = None, principal: Principal = Depends(require_perm("audit.view")),
               db: Session = Depends(get_db)):
    rows = db.scalars(_query(q, action, actor, date_from, date_to).order_by(AuditLog.ts.desc()).limit(20000))
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow(["Время", "Кто", "Действие", "Объект", "Данные"])
    for r in rows:
        i = _item(r)
        w.writerow([i["ts"], i["actor"], i["action_title"], i["target"], i["payload"]])
    data = io.BytesIO(("\ufeff" + buf.getvalue()).encode("utf-8"))
    return StreamingResponse(data, media_type="text/csv; charset=utf-8",
                             headers={"Content-Disposition": 'attachment; filename="audit.csv"'})
