"""API вкладки «График» (16.3): сетка месяца, ручные смены, отсутствия, заявления, выгрузки.

Правила — в прикладном слое: ``schedule_grid.py`` (сетка и выгрузки), ``schedule_edit.py``
(правки) и ``absence_statement.py`` (заявления). Роутер разбирает запрос и проверяет право.
"""
from __future__ import annotations

import datetime as dt
from typing import Optional

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.core.auth import Principal
from app.core.db import get_db
from app.core.permissions import require_perm
from app.core.schemas import Ok
from app.modules.exchange.application.tables import XLSX_MEDIA_TYPE, attachment

from ..application import absence_statement, schedule_edit, schedule_grid
from ..application.schedule_edit import AbsenceIn, ClearMonthIn, ManualShiftIn, RangeAbsenceIn
from .schemas import (
    AbsenceAddedOut,
    AbsencePeriodOut,
    GridOut,
    RangeAbsenceOut,
    ResetMonthOut,
    TimeoffHoursOut,
)

router = APIRouter(prefix="/api/schedule", tags=["schedule"])


@router.get("", response_model=GridOut)
def get_grid(year: int, month: int, principal: Principal = Depends(require_perm("schedule.view")),
             db: Session = Depends(get_db)):
    """Сетка Графика: ФИО × дни месяца."""
    return schedule_grid.grid(db, principal, year, month)


@router.put("/shift", response_model=Ok)
def put_manual_shift(payload: ManualShiftIn, principal: Principal = Depends(require_perm("schedule.edit")),
                     db: Session = Depends(get_db)):
    schedule_edit.put_manual_shift(db, principal, payload)
    return Ok()


@router.delete("/shift", response_model=Ok)
def delete_manual_shift(employee_id: int, date: dt.date,
                        principal: Principal = Depends(require_perm("schedule.edit")),
                        db: Session = Depends(get_db)):
    """Удаление ручной смены — день возвращается к генерации из Табеля."""
    schedule_edit.delete_manual_shift(db, principal, employee_id, date)
    return Ok()


@router.post("/absence", response_model=AbsenceAddedOut)
def add_absence(payload: AbsenceIn, principal: Principal = Depends(require_perm("schedule.edit")),
                db: Session = Depends(get_db)):
    """«Пропуск/отлучка» — согласованное отсутствие на часть смены или на всю смену."""
    return {"ok": True, "id": schedule_edit.add_absence(db, principal, payload)}


@router.delete("/absence/{absence_id}", response_model=Ok)
def remove_absence(absence_id: int, principal: Principal = Depends(require_perm("schedule.edit")),
                   db: Session = Depends(get_db)):
    schedule_edit.remove_absence(db, principal, absence_id)
    return Ok()


@router.post("/range-absence", response_model=RangeAbsenceOut)
def range_absence(payload: RangeAbsenceIn, principal: Principal = Depends(require_perm("schedule.edit")),
                  db: Session = Depends(get_db)):
    """«Назначить отсутствие» на период: кодом Табеля либо согласованным отсутствием Графика."""
    return schedule_edit.range_absence(db, principal, payload)


@router.get("/timeoff-hours", response_model=TimeoffHoursOut)
def timeoff_hours(employee_id: int, date: dt.date,
                  principal: Principal = Depends(require_perm("schedule.view")), db: Session = Depends(get_db)):
    """Часы «выходного за ранее отработанные часы» для сотрудника и дня."""
    return absence_statement.timeoff_hours(db, employee_id, date)


@router.get("/absence-period", response_model=AbsencePeriodOut)
def absence_period(employee_id: int, date: dt.date, absence_id: Optional[int] = None,
                   principal: Principal = Depends(require_perm("schedule.view")),
                   db: Session = Depends(get_db)):
    """Непрерывный период одного отсутствия вокруг даты — для печати заявления."""
    return absence_statement.absence_period(db, employee_id, date, absence_id)


@router.post("/reset-month", response_model=ResetMonthOut)
def reset_month(payload: ClearMonthIn, principal: Principal = Depends(require_perm("schedule.edit")),
                db: Session = Depends(get_db)):
    """«Сбросить месяц»: убрать ручные смены и согласованные отсутствия, График — из Табеля."""
    return schedule_edit.reset_month(db, principal, payload)


@router.get("/xlsx", response_class=Response)
def export_xlsx(year: int, month: int, principal: Principal = Depends(require_perm("schedule.edit")),
                db: Session = Depends(get_db)):
    """График в Excel."""
    content, filename = schedule_grid.export_xlsx(db, principal, year, month)
    return Response(content=content, media_type=XLSX_MEDIA_TYPE, headers=attachment(filename))


@router.get("/pdf", response_class=Response)
def export_pdf(year: int, month: int, principal: Principal = Depends(require_perm("schedule.view")),
               db: Session = Depends(get_db)):
    """График на месяц в PDF: та же таблица, что в «Печать» и Excel."""
    content, filename = schedule_grid.export_pdf(db, principal, year, month)
    return Response(content=content, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})
