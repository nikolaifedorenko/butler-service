"""Общий запуск изменяющих операций шахматки (§4.6): предпросмотр откатывается, сохранение
коммитится; ошибки ввода — 422, конфликт версии или состояния — 409, нет права — 403."""
from __future__ import annotations

import datetime as dt

from fastapi import HTTPException, Query
from sqlalchemy.orm import Session

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


def run(db: Session, op, preview_flag: bool, window: tuple[dt.date, dt.date] | None) -> dict:
    try:
        result, d = preview.run_operation(db, op, window, TimesheetDuty(db) if window else None)
    except FundError as e:
        db.rollback()
        raise err(e) from e
    if preview_flag:
        db.rollback()          # предпросмотр: тот же код, но ничего не сохраняется
    else:
        db.commit()
    return {"preview": preview_flag, "result": result, "diff": d}
