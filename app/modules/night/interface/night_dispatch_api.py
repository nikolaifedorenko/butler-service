"""Недостатки смены и отправка их ответственным службам.

«Не ОК» и «не проверено» собираются по службам и отправляются вручную — всё или выбранное.
Отправленное помечается и повторно не уходит. Правила — в ``application/night_notify.py``."""
from __future__ import annotations

from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.auth import Principal
from app.core.db import get_db
from app.core.permissions import require_perm

from ..application import night_notify
from .night_common import DispatchIn, router
from .schemas import DefectsOut, DispatchesOut, DispatchResultOut, PreviewOut

VIEW = require_perm("night.view")


@router.get("/reports/{report_id}/defects", response_model=DefectsOut)
def report_defects(report_id: int, principal: Principal = Depends(VIEW), db: Session = Depends(get_db)):
    """Недостатки смены: позиции, группы по службам, журнал отправок, шаблон сообщения."""
    return night_notify.defects_payload(db, report_id)


@router.post("/reports/{report_id}/dispatch", response_model=DispatchResultOut, dependencies=[Depends(VIEW)])
def dispatch_report(report_id: int, payload: DispatchIn,
                    principal: Principal = Depends(require_perm("night.dispatch")),
                    db: Session = Depends(get_db)):
    """Отправить недостатки службам: всё неотправленное или выбранное."""
    return night_notify.dispatch_defects(db, principal, report_id, mode=payload.mode,
                                         item_ids=payload.item_ids, service_ids=payload.service_ids)


@router.get("/reports/{report_id}/dispatches", response_model=DispatchesOut)
def report_dispatches(report_id: int, limit: int = 50, principal: Principal = Depends(VIEW),
                      db: Session = Depends(get_db)):
    """Журнал отправок смены."""
    return {"dispatches": night_notify.report_journal(db, report_id, limit=limit)}


@router.post("/reports/{report_id}/defects/preview", response_model=PreviewOut)
def preview_defects(report_id: int, payload: DispatchIn, principal: Principal = Depends(VIEW),
                    db: Session = Depends(get_db)):
    """Предпросмотр: что именно уйдёт каждой службе."""
    return {"messages": night_notify.preview_messages(db, principal, report_id, mode=payload.mode,
                                                      item_ids=payload.item_ids, service_ids=payload.service_ids),
            "domain": night_notify.DOMAIN}
