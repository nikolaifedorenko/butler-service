"""Отчёт целиком: шаг «Проверка электрокаров», закрытие и переоткрытие смены, выгрузка
DOCX и PDF. Правила — в ``application/shift.py``."""
from __future__ import annotations

from typing import Optional

from fastapi import Depends, File, Form, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.core.auth import Principal
from app.core.db import get_db
from app.core.media import UploadRef, max_upload_bytes, read_upload_streaming
from app.core.permissions import require_perm
from app.modules.cars.application.schemas import NightCarsStateOut
from app.modules.exchange.application.documents import DOCX_MEDIA_TYPE

from ..application import shift
from .night_common import CloseSectionIn, InterceptionAck, router
from .schemas import CarCheckedOut, CarsFinishedOut, ReportChangedOut

VIEW = require_perm("night.view")
CLOSE = require_perm("night.close")


def _attachment(content: bytes, media_type: str, name: str) -> Response:
    return Response(content, media_type=media_type,
                    headers={"Content-Disposition": f'attachment; filename="{name}"'})


@router.get("/reports/{report_id}/cars", response_model=NightCarsStateOut)
def report_cars(report_id: int, principal: Principal = Depends(VIEW), db: Session = Depends(get_db)):
    """Обход электрокаров за смену: кары и отметки."""
    return shift.cars_state(db, report_id)


@router.post("/reports/{report_id}/cars/{car_id}/check", response_model=CarCheckedOut)
def report_car_check(report_id: int, car_id: int,
                     found: bool = Form(True),
                     found_location: str = Form(""),
                     moved: bool = Form(False),
                     location: str = Form(""),
                     canopy: bool = Form(True),
                     charge: str = Form(""),        # full | half | empty | ''
                     on_charge: bool = Form(False),
                     condition: str = Form("ok"),   # ok | bad
                     trash: bool = Form(False),
                     clean: bool = Form(True),
                     comment: str = Form(""),
                     file: Optional[UploadFile] = File(None),
                     principal: Principal = Depends(VIEW),
                     db: Session = Depends(get_db)):
    """Отметить кар в ночном обходе (multipart): состояние, места и фото."""
    refs: list[UploadRef] = []
    try:
        if file is not None:
            ref = read_upload_streaming(file, max_upload_bytes(db))     # сразу на диск, не в память
            if ref.size:
                refs.append(ref)
            else:
                ref.discard()
        check = shift.check_car(db, principal, report_id, car_id, found=found, found_location=found_location,
                                moved=moved, location=location, canopy=canopy, charge=charge,
                                on_charge=on_charge, condition=condition, trash=trash, clean=clean,
                                comment=comment, photo_refs=refs)
    finally:
        for ref in refs:
            ref.discard()       # файл, не перенесённый в хранилище из-за ошибки
    return {"check": check}


@router.post("/reports/{report_id}/cars/finish", response_model=CarsFinishedOut)
def report_cars_finish(report_id: int, payload: InterceptionAck, principal: Principal = Depends(VIEW),
                       db: Session = Depends(get_db)):
    """Завершить шаг «Проверка электрокаров»; с непроверенными карами — после подтверждения."""
    return shift.finish_cars(db, principal, report_id, ack=payload.ack)


@router.post("/reports/{report_id}/close", response_model=ReportChangedOut)
def close_report(report_id: int, payload: CloseSectionIn | None = None, principal: Principal = Depends(CLOSE),
                 db: Session = Depends(get_db)):
    """Закрыть смену вручную; неполную — после подтверждения."""
    return {"report": shift.close_report(db, principal, report_id,
                                         force=bool(payload and payload.force_unanswered))}


@router.post("/reports/{report_id}/reopen", response_model=ReportChangedOut)
def reopen_report(report_id: int, principal: Principal = Depends(CLOSE), db: Session = Depends(get_db)):
    """Переоткрыть закрытую смену для правок."""
    return {"report": shift.reopen_report(db, principal, report_id)}


@router.get("/reports/{report_id}/export.docx", response_class=Response)
def export_docx(report_id: int, principal: Principal = Depends(VIEW), db: Session = Depends(get_db)):
    docx, name = shift.export_docx(db, report_id)
    return _attachment(docx, DOCX_MEDIA_TYPE, name)


@router.get("/reports/{report_id}/export.pdf", response_class=Response)
def export_pdf(report_id: int, principal: Principal = Depends(VIEW), db: Session = Depends(get_db)):
    pdf, name = shift.export_pdf(db, report_id)
    return _attachment(pdf, "application/pdf", name)
