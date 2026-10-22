"""Недостатки смены и отправка их ответственным службам (этап 5 ночного отчёта v2)."""
from __future__ import annotations

from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.auth import Principal
from app.core.db import get_db
from app.core.permissions import require_perm

from ..application.night import (
    defects_of,
)
from .night_common import (
    DispatchIn,
    _get_report,
    router,
)

# ─────────────── недостатки смены и отправка службам (этап 5) ───────────────
# Экран консолидированной отправки: «Не ОК» и «Не проверено» группируются по
# ответственным службам, отправляются вручную (всё или выбранное), отправленное
# помечается. Исправленное ПОСЛЕ отправки повторно не уходит и не отзывается.
# Отправка — право night.dispatch (В-5), по умолчанию у всех ролей.

@router.get("/reports/{report_id}/defects")
def report_defects(report_id: int, principal: Principal = Depends(require_perm("night.view")),
                   db: Session = Depends(get_db)):
    """Недостатки смены: позиции, группы по службам, журнал, шаблон сообщения."""
    from ..application.night_notify import defects_payload

    rep = _get_report(db, report_id)
    return defects_payload(db, rep)


@router.post("/reports/{report_id}/dispatch", dependencies=[Depends(require_perm("night.view"))])
def dispatch_report(report_id: int, payload: DispatchIn,
                    principal: Principal = Depends(require_perm("night.dispatch")),
                    db: Session = Depends(get_db)):
    """Отправить недостатки службам: всё скопом или выбранное (только вручную)."""
    from ..application.night_notify import dispatch_defects

    rep = _get_report(db, report_id)
    res = dispatch_defects(db, rep, principal, mode=payload.mode,
                           item_ids=payload.item_ids, service_ids=payload.service_ids)
    return res


@router.get("/reports/{report_id}/dispatches")
def report_dispatches(report_id: int, limit: int = 50,
                      principal: Principal = Depends(require_perm("night.view")),
                      db: Session = Depends(get_db)):
    """Журнал отправок смены — строки общего журнала раздела «Ночной отчёт»."""
    from ..application.night_notify import report_journal

    rep = _get_report(db, report_id)
    return {"dispatches": report_journal(db, rep, limit=limit)}


@router.post("/reports/{report_id}/defects/preview")
def preview_defects(report_id: int, payload: DispatchIn,
                    principal: Principal = Depends(require_perm("night.view")),
                    db: Session = Depends(get_db)):
    """Предпросмотр сообщений: что именно уйдёт каждой службе (без отправки)."""
    from app.modules.notify.application.recipients import group_by_service

    from ..application.night_notify import DOMAIN, preview_message

    rep = _get_report(db, report_id)
    data = defects_of(db, rep)
    rows = [d for d in data["items"] if d["sendable"]]
    if payload.mode == "selected":
        wanted = {int(i) for i in payload.item_ids}
        rows = [d for d in rows if d["id"] in wanted]
    if payload.service_ids:
        allowed = {int(i) for i in payload.service_ids}
        rows = [d for d in rows if d.get("service_id") in allowed]
    out = []
    for group in group_by_service(db, rows):
        if not [d for d in group["defects"] if d["sendable"]]:
            continue
        out.append({"service_id": group["service_id"], "service_name": group["service_name"],
                    "channels": group["channels"], "problems": group["problems"],
                    "defects": group["counts"]["sendable"],
                    "message": preview_message(db, rep, group, principal.name)})
    return {"ok": True, "messages": out, "domain": DOMAIN}
