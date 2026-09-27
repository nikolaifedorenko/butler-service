"""Виды заявлений (расширяемый словарь statement_kinds) и фирменные бланки .docx.

Вид заявления = код + название + текст-заполнитель с плейсхолдерами {field}.
Виды создаёт менеджер/админ в «Настройки → Виды заявлений и шаблоны»; к виду
привязывается смена словаря (ShiftType.doc_type) — из ячейки графика печатается
документ. Фирменный бланк templates/<code>.docx перекрывает текст-заполнитель:
оформление бланка сохраняется, плейсхолдеры подставляются в его run'ы.
"""
from __future__ import annotations

import datetime as dt
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import Principal, audit, require_manager
from ..db import get_db
from ..doc_templates import load_doc_templates
from ..doc_render import (
    CODE_RE, PLACEHOLDER_HELP, build_sample_docx, build_values, delete_template,
    hours_text, pdf_available, pdf_status, render_docx, save_template,
    scan_placeholders, template_path,
)
from ..pdf_render import docx_to_pdf
from ..models import Employee, ShiftType, StatementKind

router = APIRouter(prefix="/api/docs", tags=["docs"])

# встроенные виды: каким текстом из настроек печатать, если у вида пустой text
FALLBACK_TEXT_KEY = {"vacation_paid": "vacation", "vacation_unpaid": "vacation_unpaid",
                     "day_off_hours": "day_off_hours", "time_off_request": "time_off_request"}


def _legacy_fallback_text(doc_cfg: dict, code: str) -> str:
    """Для встроенных видов с пустым текстом — прежний шаблон из настроек."""
    key = FALLBACK_TEXT_KEY.get(code)
    if key and key in doc_cfg:
        return doc_cfg[key]
    return doc_cfg["vacation"]


def _hours_between(from_time: str, until_time: str) -> float:
    """Сколько часов между «с 14:00» и «до 16:00» (через полночь — тоже считается)."""
    try:
        fh, fm = (int(x) for x in from_time.split(":"))
        th, tm = (int(x) for x in until_time.split(":"))
    except ValueError:
        return 0.0
    mins = (th * 60 + tm) - (fh * 60 + fm)
    if mins <= 0:
        mins += 24 * 60
    return round(mins / 60.0, 2)


def _kind_or_422(db: Session, code: str) -> StatementKind:
    kind = db.scalar(select(StatementKind).where(StatementKind.code == code))
    if not kind:
        raise HTTPException(status_code=422, detail=f"Неизвестный вид заявления: {code}")
    return kind


def _kind_dict(k: StatementKind) -> dict:
    p = template_path(k.code)
    return {"id": k.id, "code": k.code, "name": k.name, "text": k.text,
            "builtin": bool(k.builtin), "active": bool(k.active), "sort_order": k.sort_order,
            "template": {"uploaded": p is not None,
                         "filename": p.name if p else None,
                         "size": p.stat().st_size if p else 0,
                         "placeholders": sorted(scan_placeholders(p)) if p else []}}


# ─────────────────────────── виды заявлений (CRUD) ───────────────────────────
@router.get("/kinds")
def list_kinds(principal: Principal = Depends(require_manager), db: Session = Depends(get_db)):
    kinds = db.scalars(select(StatementKind).order_by(
        StatementKind.sort_order, StatementKind.name)).all()
    return {"kinds": [_kind_dict(k) for k in kinds],
            "placeholders": PLACEHOLDER_HELP,
            "pdf_available": pdf_available(), "pdf": pdf_status()}


class KindIn(BaseModel):
    code: str
    name: str
    text: str = ""


class KindUpdate(BaseModel):
    name: str
    text: str = ""
    active: bool = True
    sort_order: int = 100


@router.post("/kinds")
def create_kind(payload: KindIn, principal: Principal = Depends(require_manager),
                db: Session = Depends(get_db)):
    code = payload.code.strip().lower()
    if not CODE_RE.match(code):
        raise HTTPException(status_code=422,
                            detail="Код вида: строчная латиница, цифры и «_», 2–40 символов, "
                                   "начинается с буквы (например mat_aid)")
    if not payload.name.strip():
        raise HTTPException(status_code=422, detail="Название вида заявления не может быть пустым")
    if db.scalar(select(StatementKind).where(StatementKind.code == code)):
        raise HTTPException(status_code=409, detail=f"Вид заявления с кодом «{code}» уже есть")
    kind = StatementKind(code=code, name=payload.name.strip(), text=payload.text)
    db.add(kind)
    audit(db, principal, "statement_kind_create", code, {"name": kind.name})
    db.commit()
    return _kind_dict(kind)


@router.put("/kinds/{kind_id}")
def update_kind(kind_id: int, payload: KindUpdate,
                principal: Principal = Depends(require_manager), db: Session = Depends(get_db)):
    kind = db.get(StatementKind, kind_id)
    if not kind:
        raise HTTPException(status_code=404, detail="Вид заявления не найден")
    if not payload.name.strip():
        raise HTTPException(status_code=422, detail="Название вида заявления не может быть пустым")
    kind.name = payload.name.strip()
    kind.text = payload.text
    kind.active = payload.active
    kind.sort_order = payload.sort_order
    audit(db, principal, "statement_kind_update", kind.code, {"name": kind.name})
    db.commit()
    return _kind_dict(kind)


@router.delete("/kinds/{kind_id}")
def delete_kind(kind_id: int, principal: Principal = Depends(require_manager),
                db: Session = Depends(get_db)):
    """Удалить вид заявления: у привязанных смен словаря doc_type очищается,
    фирменный бланк (если был загружен) удаляется с диска."""
    kind = db.get(StatementKind, kind_id)
    if not kind:
        raise HTTPException(status_code=404, detail="Вид заявления не найден")
    refs = db.scalars(select(ShiftType).where(ShiftType.doc_type == kind.code)).all()
    for st in refs:
        st.doc_type = ""
    delete_template(kind.code)
    db.delete(kind)
    audit(db, principal, "statement_kind_delete", kind.code,
          {"name": kind.name, "shifts_cleared": [s.code for s in refs]})
    db.commit()
    return {"ok": True, "shifts_cleared": len(refs)}


# ─────────────────────────── фирменные бланки .docx ───────────────────────────
@router.get("/templates")
def get_templates(principal: Principal = Depends(require_manager), db: Session = Depends(get_db)):
    """Сводка по бланкам: какие виды есть, у каких загружен фирменный .docx."""
    kinds = db.scalars(select(StatementKind).order_by(
        StatementKind.sort_order, StatementKind.name)).all()
    return {"types": {k.code: k.name for k in kinds},
            "placeholders": PLACEHOLDER_HELP,
            "templates": [_kind_dict(k)["template"] | {"type": k.code, "title": k.name}
                          for k in kinds],
            "pdf_available": pdf_available(), "pdf": pdf_status()}


@router.get("/sample")
def sample_template(type: str, principal: Principal = Depends(require_manager),
                    db: Session = Depends(get_db)):
    """Образец .docx с плейсхолдерами — скачать, оформить под фирменный бланк и загрузить."""
    kind = _kind_or_422(db, type)
    return Response(content=build_sample_docx(kind.code, kind.text),
                    media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    headers={"Content-Disposition": f'attachment; filename="sample_{kind.code}.docx"'})


@router.post("/templates")
async def upload_template(type: str, file: UploadFile,
                          principal: Principal = Depends(require_manager),
                          db: Session = Depends(get_db)):
    _kind_or_422(db, type)
    data = await file.read()
    if len(data) > 5 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Файл больше 5 МБ")
    try:
        meta = save_template(type, data)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    audit(db, principal, "doc_template_upload", type, {"filename": file.filename})
    db.commit()
    return {"ok": True, **meta}


@router.delete("/templates")
def remove_template(type: str, principal: Principal = Depends(require_manager),
                    db: Session = Depends(get_db)):
    _kind_or_422(db, type)
    removed = delete_template(type)
    audit(db, principal, "doc_template_delete", type, {})
    db.commit()
    return {"ok": True, "removed": removed}


# ─────────────────────────── рендер документа ───────────────────────────
class RenderIn(BaseModel):
    type: str
    employee_id: int
    date_from: str
    date_to: str
    format: str = "docx"        # docx | pdf
    from_time: str = ""         # «отпросился с 14:00…»
    until_time: str = ""        # «…до 16:00»
    hours: Optional[float] = None
    reason: str = ""            # вид отсутствия из словаря («Отпуск», «Выходной за часы»…)
    note: str = ""              # примечание из ячейки графика (приказ, причина)


@router.post("/render")
def render(payload: RenderIn, principal: Principal = Depends(require_manager),
           db: Session = Depends(get_db)):
    kind = _kind_or_422(db, payload.type)
    emp = db.get(Employee, payload.employee_id)
    if not emp:
        raise HTTPException(status_code=404, detail="Сотрудник не найден")
    try:
        d1 = dt.date.fromisoformat(payload.date_from)
        d2 = dt.date.fromisoformat(payload.date_to)
    except ValueError:
        raise HTTPException(status_code=422, detail="Даты должны быть в формате ГГГГ-ММ-ДД")
    if d2 < d1:
        raise HTTPException(status_code=422, detail="Дата окончания раньше даты начала")

    doc_cfg = load_doc_templates(db)
    hours_val = payload.hours
    if hours_val is None and payload.from_time and payload.until_time:
        hours_val = _hours_between(payload.from_time, payload.until_time)
    values = build_values(emp, d1, d2, extra={
        "company": doc_cfg["company"], "director": doc_cfg["director"],
        "from_time": payload.from_time, "until_time": payload.until_time,
        "hours": hours_val or 0, "reason": payload.reason, "note": payload.note})
    # текст-заполнитель вида; для встроенных видов без текста — прежние шаблоны из настроек
    fallback = (kind.text or "").strip() or _legacy_fallback_text(doc_cfg, kind.code)
    docx_bytes = render_docx(kind.code, values, fallback)

    audit(db, principal, "doc_render", kind.code,
          {"employee": emp.full_name, "period": f"{d1}..{d2}", "format": payload.format,
           "time": f"{payload.from_time}-{payload.until_time}" if payload.from_time else ""})
    db.commit()

    if payload.format == "docx":
        return Response(content=docx_bytes,
                        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        headers={"Content-Disposition":
                                 f'attachment; filename="{kind.code}_{d1.isoformat()}_{emp.id}.docx"'})
    pdf, how = docx_to_pdf(docx_bytes, f"{kind.code}_{emp.id}.pdf")
    if pdf is None:
        raise HTTPException(status_code=501,
                            detail=f"PDF собрать не удалось: {how}. Скачайте DOCX — он откроется "
                                   "в Word/Pages/LibreOffice, из него можно напечатать напрямую.")
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition":
                             f'attachment; filename="{kind.code}_{d1.isoformat()}_{emp.id}.pdf"'})
