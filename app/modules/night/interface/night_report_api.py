"""Отчёт целиком: шаг «Проверка электрокаров», ручное закрытие и переоткрытие, выгрузка
DOCX/PDF."""
from __future__ import annotations

from typing import Optional

from fastapi import Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.core.audit import audit
from app.core.auth import Principal
from app.core.db import get_db
from app.core.media import (
    UploadRef,
    max_upload_bytes,
    photos_of,
    read_upload_streaming,
)
from app.core.permissions import require_perm
from app.core.settings_store import Setting
from app.core.time import now_local

from ..adapters.orm import (
    NightAreaSection,
    NightReport,
)
from ..application.night import (
    finalize_report,
)
from .night_common import (
    CloseSectionIn,
    InterceptionAck,
    _get_report,
    _guard_open,
    _principal_name,
    _report_payload,
    router,
)

# ─────────────────────────── отдача файлов фото ───────────────────────────

# ─────────────────────────── шаг «Проверка электрокаров» ───────────────────────────

def _cars_section(rep: NightReport) -> NightAreaSection:
    for s in rep.areas:
        if s.area_id is None and s.category == "cars":
            return s
    raise HTTPException(status_code=404, detail="Шаг «Проверка электрокаров» не найден в отчёте")


@router.get("/reports/{report_id}/cars")
def report_cars(report_id: int, principal: Principal = Depends(require_perm("night.view")),
                db: Session = Depends(get_db)):
    """Состояние обхода электрокаров за смену (список каров + отметки)."""
    from app.modules.cars.application.cars import night_cars_state

    rep = _get_report(db, report_id)
    return night_cars_state(db, rep)


@router.post("/reports/{report_id}/cars/{car_id}/check")
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
                     principal: Principal = Depends(require_perm("night.view")),
                     db: Session = Depends(get_db)):
    """Отметить кар в ходе ночного обхода (перезапись — last write wins).

    Форма та же, что у окна возврата кара («Электрокары» → «Вернул»): место из
    справочника, заряд, чекбоксы состояния, комментарий и фото-доказательство
    (оригинал, до 12 МБ) — плюс чекбокс «Кар найден на месте».

    Места два: `found_location` — где батлер нашёл кар, `location` — куда
    переставил (`moved=True`): кар мог стоять не там, что в карточке, а найденный
    кар батлер мог перепарковать. Перепарковка — факт, не замечание.

    Отметки пишутся в общую базу: состояние карточки кара обновляется.
    «Не ОК» и «кар не найден» идут в замечания супервайзеру; отсутствие тента —
    просто факт, в замечания не входит."""
    from sqlalchemy.exc import IntegrityError

    from app.modules.cars.application.cars import CarOpError, check_car_night
    from app.modules.cars.application.catalog import Car

    rep = _get_report(db, report_id)
    _guard_open(rep)
    car = db.get(Car, car_id)
    if car is None:
        raise HTTPException(status_code=404, detail="Кар не найден")
    sec = _cars_section(rep)

    refs: list[UploadRef] = []
    try:
        if file is not None:
            limit = max_upload_bytes(db)
            # потоковая загрузка: чанки сразу на диск, не в память (P1 20.10.2026)
            ref = read_upload_streaming(file, limit)
            if ref.size:
                refs.append(ref)
            else:
                ref.discard()      # пустой файл не сохраняем (прежнее поведение: if blob)
        res = check_car_night(db, rep, car, principal, found=found,
                              found_location=found_location, moved=moved,
                              location=location, canopy=canopy,
                              charge=charge, on_charge=on_charge,
                              condition=condition, trash=trash,
                              clean=clean, comment=comment, photo_refs=refs)
    except CarOpError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ValueError as e:       # не-картинка в фото
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        for ref in refs:
            ref.discard()   # не потреблённые при ошибке; потреблённые уже перенесены (missing_ok)
    # если область-шаг ещё не закреплена за кем-то — закрепляем (как при ответе на пункт)
    if sec.status == "free":
        sec.status = "taken"
        sec.taken_by = principal.user.id
        sec.taken_by_name = _principal_name(principal)
        sec.taken_at = now_local()
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Повторная отметка — обновите список")
    return {"ok": True, "check": res}


@router.post("/reports/{report_id}/cars/finish")
def report_cars_finish(report_id: int, payload: InterceptionAck,
                       principal: Principal = Depends(require_perm("night.view")),
                       db: Session = Depends(get_db)):
    """Завершить шаг «Проверка электрокаров». Незакрытые кары — только после подтверждения."""
    from app.modules.cars.application.cars import CarOpError, finish_cars_step, night_cars_state

    rep = _get_report(db, report_id)
    _guard_open(rep)
    state = night_cars_state(db, rep)
    if state["unchecked"] > 0 and not payload.ack:
        raise HTTPException(status_code=409, detail={
            "interception": False,
            "message": f"Не проверено каров: {state['unchecked']}. Завершить шаг всё равно?"})
    try:
        res = finish_cars_step(db, rep, principal)
    except CarOpError as e:
        raise HTTPException(status_code=409, detail=str(e))
    sec = _cars_section(rep)
    if sec.status != "done":
        sec.status = "done"
        sec.closed_at = now_local()
        sec.closed_by = principal.user.id
    audit(db, principal, "night_cars_finish", f"report:{rep.id}",
          {"checked": state["checked"], "unchecked": state["unchecked"]})
    db.commit()
    return {"ok": True, **res}


# ─────────────────────────── закрытие отчёта вручную ───────────────────────────

@router.post("/reports/{report_id}/close")
def close_report(report_id: int, payload: CloseSectionIn | None = None,
                 principal: Principal = Depends(require_perm("night.close")),
                 db: Session = Depends(get_db)):
    rep = _get_report(db, report_id)
    if rep.status == "closed":
        raise HTTPException(status_code=409, detail="Отчёт уже закрыт")
    unfinished = [s for s in rep.areas if s.status != "done"]
    force = bool(payload and payload.force_unanswered)
    if (unfinished or not rep.cars_step_done) and not force:
        parts = []
        if unfinished:
            parts.append(f"незакрытых областей: {len(unfinished)}")
        if not rep.cars_step_done:
            parts.append("шаг «Проверка электрокаров» не завершён")
        raise HTTPException(status_code=409, detail={
            "unanswered": len(unfinished),
            "message": "Смена будет неполной (" + ", ".join(parts) + "). Закрыть всё равно?"})
    finalize_report(rep, reason="manual")
    audit(db, principal, "night_report_close", f"report:{rep.id}", {"result": rep.result})
    db.commit()
    return {"ok": True, "report": _report_payload(db, rep)}


@router.post("/reports/{report_id}/reopen")
def reopen_report(report_id: int, principal: Principal = Depends(require_perm("night.close")),
                  db: Session = Depends(get_db)):
    """Переоткрыть закрытый отчёт для правок.

    Автозакрытие для переоткрытого отчёта выключается (reopened_at): фоновая
    синхронизация больше его не закрывает — иначе переоткрытие «жило» бы меньше
    двух минут, а правки падали в 409 «Смена закрыта» (ревью 20.10.2026, P1).
    Повторно закрывает смену сам менеджер («Закрыть смену»)."""
    rep = _get_report(db, report_id)
    if rep.status != "closed":
        raise HTTPException(status_code=409, detail="Отчёт не закрыт — переоткрывать нечего")
    rep.status = "open"
    rep.result = ""
    rep.closed_at = None
    rep.close_reason = ""
    rep.reopened_at = now_local()
    audit(db, principal, "night_report_reopen", f"report:{rep.id}", {})
    db.commit()
    return {"ok": True, "report": _report_payload(db, rep)}


# ─────────────────────────── выгрузка ───────────────────────────

def _company(db: Session) -> str:
    s = db.get(Setting, "doc_company")
    return (s.value if s and s.value else "")


@router.get("/reports/{report_id}/export.docx")
def export_docx(report_id: int, principal: Principal = Depends(require_perm("night.view")),
                db: Session = Depends(get_db)):
    from ..application.night_export import render_night_report_docx

    rep = _get_report(db, report_id)
    item_ids = [i.id for s in rep.areas for i in s.items]
    pmap = photos_of(db, "night_item", item_ids)
    docx = render_night_report_docx(db, rep.id, company=_company(db), photos_map=pmap)
    name = f"night-{rep.date.isoformat()}.docx"
    return Response(docx, media_type=(
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
        headers={"Content-Disposition": f'attachment; filename="{name}"'})


@router.get("/reports/{report_id}/export.pdf")
def export_pdf(report_id: int, principal: Principal = Depends(require_perm("night.view")),
               db: Session = Depends(get_db)):
    from app.core.render import docx_to_pdf

    from ..application.night_export import render_night_report_docx

    rep = _get_report(db, report_id)
    item_ids = [i.id for s in rep.areas for i in s.items]
    pmap = photos_of(db, "night_item", item_ids)
    docx = render_night_report_docx(db, rep.id, company=_company(db), photos_map=pmap)
    pdf, err = docx_to_pdf(docx, filename=f"night-{rep.date.isoformat()}.pdf")
    if pdf is None:
        raise HTTPException(status_code=422, detail=err or "PDF недоступен на этом сервере")
    return Response(pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="night-{rep.date.isoformat()}.pdf"'})
