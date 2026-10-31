"""Общий запуск изменяющих операций шахматки (§4.6): предпросмотр откатывается, сохранение
коммитится; ошибки ввода — 422, конфликт версии или состояния — 409, нет права — 403; новый
овербукинг без права stays.overbook — 409 с предпросмотром (часть 2 §7)."""
from __future__ import annotations

import datetime as dt

from fastapi import HTTPException, Query
from sqlalchemy.orm import Session

from app.core.auth import Principal

from ..adapters.duty_timesheet import TimesheetDuty
from ..application import preview
from ..application.coverage import CoverageForbidden
from ..application.fund import FundConflict, FundError
from ..application.reservations import ReservationConflict

PREVIEW = Query(False, alias="preview", description="Только показать, что изменится, без сохранения")


def err(e: FundError) -> HTTPException:
    if isinstance(e, CoverageForbidden):
        return HTTPException(status_code=403, detail=str(e))
    conflict = isinstance(e, (ReservationConflict, FundConflict))
    return HTTPException(status_code=409 if conflict else 422, detail=str(e))


def run(db: Session, op, preview_flag: bool, window: tuple[dt.date, dt.date] | None,
        principal: Principal) -> dict:
    """Новый овербукинг без права stays.overbook: сохранение — 409 с предпросмотром
    (detail.diff), предпросмотр — обычный ответ с overbook_refused (текст, почему не сохранится)."""
    refused = None
    try:
        result, d = preview.run_operation(db, op, window, TimesheetDuty(db) if window else None,
                                          may_overbook="stays.overbook" in principal.gate_permissions)
    except FundError as e:
        db.rollback()
        raise err(e) from e
    except preview.OverbookRefused as e:
        db.rollback()
        if not preview_flag:
            raise HTTPException(status_code=409, detail={"message": e.text, "overbook": True, "diff": e.diff}) from e
        refused, result, d = e.text, None, e.diff
    if preview_flag:
        db.rollback()          # предпросмотр: тот же код, но ничего не сохраняется
    else:
        db.commit()
    out = {"preview": preview_flag, "result": result, "diff": d}
    if refused is not None:
        out["overbook_refused"] = refused
    return out
