"""Ход смены: отчёт дня и архив, взять и закрыть объект, отметки пунктов, фото.
Правила — в ``application/shift.py``."""
from __future__ import annotations

from fastapi import Depends, File, UploadFile
from sqlalchemy.orm import Session

from app.core.auth import Principal
from app.core.db import get_db
from app.core.media import max_upload_bytes, read_upload_streaming
from app.core.permissions import require_perm

from ..application import shift
from .night_common import AnswerIn, CloseSectionIn, InterceptionAck, router
from .schemas import (
    ItemAnsweredOut,
    ItemPhotoOut,
    ReportEnvelopeOut,
    ReportsOut,
    SectionChangedOut,
    SectionTakenOut,
    TodayPendingOut,
    TodayReportOut,
)

VIEW = require_perm("night.view")
CLOSE = require_perm("night.close")


@router.get("/today", response_model=TodayReportOut | TodayPendingOut)
def today_report(principal: Principal = Depends(VIEW), db: Session = Depends(get_db)):
    """Отчёт текущей ночной смены либо пояснение, почему его ещё нет."""
    return shift.current_report(db)


@router.get("/reports", response_model=ReportsOut)
def list_reports(limit: int = 60, principal: Principal = Depends(VIEW), db: Session = Depends(get_db)):
    """Архив ночных отчётов с итогами."""
    return {"reports": shift.list_reports(db, limit)}


@router.get("/reports/{report_id}", response_model=ReportEnvelopeOut)
def get_report(report_id: int, principal: Principal = Depends(VIEW), db: Session = Depends(get_db)):
    return {"report": shift.report(db, report_id)}


@router.post("/sections/{section_id}/take", response_model=SectionTakenOut)
def take_section(section_id: int, payload: InterceptionAck, principal: Principal = Depends(VIEW),
                 db: Session = Depends(get_db)):
    """Взять объект в работу; объект, который ведёт другой, — после подтверждения."""
    return shift.take_section(db, principal, section_id, ack=payload.ack)


@router.post("/sections/{section_id}/close", response_model=SectionChangedOut)
def close_section(section_id: int, payload: CloseSectionIn | None = None, principal: Principal = Depends(VIEW),
                  db: Session = Depends(get_db)):
    """Завершить проверку объекта; с неотмеченными пунктами — после подтверждения."""
    return {"section": shift.close_section(db, principal, section_id,
                                           force_unanswered=bool(payload and payload.force_unanswered))}


@router.post("/sections/{section_id}/reopen", response_model=SectionChangedOut)
def reopen_section(section_id: int, principal: Principal = Depends(CLOSE), db: Session = Depends(get_db)):
    return {"section": shift.reopen_section(db, principal, section_id)}


@router.put("/items/{item_id}/answer", response_model=ItemAnsweredOut)
def answer_item(item_id: int, payload: AnswerIn, principal: Principal = Depends(VIEW),
                db: Session = Depends(get_db)):
    """Отметить пункт: ОК, не ОК или снять отметку."""
    return {"item": shift.answer_item(db, principal, item_id, payload.answer, payload.comment)}


@router.post("/items/{item_id}/photo", response_model=ItemPhotoOut)
def add_item_photo(item_id: int, file: UploadFile = File(...), principal: Principal = Depends(VIEW),
                   db: Session = Depends(get_db)):
    ref = read_upload_streaming(file, max_upload_bytes(db))     # сразу на диск, не в память
    try:
        return {"photo": shift.add_item_photo(db, principal, item_id, ref)}
    finally:
        ref.discard()       # файл, не перенесённый в хранилище из-за ошибки
