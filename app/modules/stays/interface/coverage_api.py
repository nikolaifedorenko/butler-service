"""API покрытия батлерами (§4.2, §4.5, §5): шаблоны, правка по дням, подбор и подмена,
«добавить смену в График». Изменяющие маршруты — с предпросмотром (§4.6).

Правила — в прикладном слое: ``application/coverage_edit.py``. Роутер разбирает запрос и
проверяет право.
"""
from __future__ import annotations

import datetime as dt
from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.auth import Principal
from app.core.db import get_db
from app.core.permissions import require_perm
from app.core.schemas import Ok

from ..adapters.duty_timesheet import TimesheetDuty
from ..application import coverage_edit
from ..application.coverage_forms import AddShiftIn, DayIn, DaysIn, TemplateIn
from ._ops import PREVIEW
from .schemas import (
    CoverageCandidateOut,
    CoverageLineOut,
    CoverageWrittenOut,
    PreviewedOut,
    ReplacementRowOut,
)

router = APIRouter(prefix="/api/stays/coverage", tags=["stays"])
ASSIGN = require_perm("stays.assign")
READ_BOARD = require_perm("stays.assign", "stays.view")      # подбор кандидатов и замены — чтение


@router.post("/template", response_model=PreviewedOut[CoverageWrittenOut])
def template(payload: TemplateIn, preview_flag: bool = PREVIEW, principal: Principal = Depends(ASSIGN),
             db: Session = Depends(get_db)):
    return coverage_edit.template(db, principal, payload, preview_only=preview_flag, duty=TimesheetDuty(db))


@router.put("/day", response_model=PreviewedOut[CoverageLineOut])
def set_day(payload: DayIn, preview_flag: bool = PREVIEW, principal: Principal = Depends(ASSIGN),
            db: Session = Depends(get_db)):
    return coverage_edit.set_day(db, principal, payload, preview_only=preview_flag, duty=TimesheetDuty(db))


@router.put("/days", response_model=PreviewedOut[CoverageWrittenOut])
def set_days(payload: DaysIn, preview_flag: bool = PREVIEW, principal: Principal = Depends(ASSIGN),
             db: Session = Depends(get_db)):
    """Назначение по дням (§6 «по дням»): одна операция, один предпросмотр."""
    return coverage_edit.set_days(db, principal, payload, preview_only=preview_flag, duty=TimesheetDuty(db))


@router.delete("/{line_id}", response_model=PreviewedOut[Ok])
def remove_line(line_id: int, preview_flag: bool = PREVIEW, principal: Principal = Depends(ASSIGN),
                db: Session = Depends(get_db)):
    return coverage_edit.remove_line(db, principal, line_id, preview_only=preview_flag, duty=TimesheetDuty(db))


@router.get("/candidates", response_model=list[CoverageCandidateOut])
def get_candidates(day: dt.date, reservation_id: Optional[int] = None, group_id: Optional[int] = None,
                   guest_ids: str = "", principal: Principal = Depends(READ_BOARD), db: Session = Depends(get_db)):
    return coverage_edit.candidates(db, day, reservation_id, group_id, guest_ids, TimesheetDuty(db))


@router.get("/replacements", response_model=list[ReplacementRowOut])
def get_replacements(first: dt.date, last: dt.date, principal: Principal = Depends(READ_BOARD),
                     db: Session = Depends(get_db)):
    return coverage_edit.replacements(db, first, last, TimesheetDuty(db))


@router.post("/add-shift", response_model=Ok)
def add_shift(payload: AddShiftIn, principal: Principal = Depends(ASSIGN), db: Session = Depends(get_db)):
    """Смена Графика для батлера «вне смены»: два права, две записи журнала (§5)."""
    return coverage_edit.add_shift(db, principal, payload)
