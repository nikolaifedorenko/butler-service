"""Виды заявлений, фирменные бланки и формирование заявления.

Вид заявления — код, название и текст с плейсхолдерами ``{field}``. Виды заводит объект в
«Настройки → Виды заявлений и шаблоны»; к виду привязывается смена словаря — из ячейки
графика печатается документ. Фирменный бланк ``<код>.docx`` перекрывает текст вида:
оформление бланка сохраняется, плейсхолдеры подставляются в него.

Бланк — файл на диске: он не откатывается вместе с транзакцией. Поэтому файл удаляется
после записи в базу, а загружается после всех проверок.
"""
from __future__ import annotations

import datetime as dt
from typing import Optional

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.audit import audit
from app.core.auth import Principal
from app.core.db import transaction, transactional
from app.core.errors import Conflict, NotFound, NotSupported, PayloadTooLarge, Validation
from app.core.format import hours_text
from app.modules.exchange.application.documents import DOCX_MEDIA_TYPE, docx_to_pdf
from app.modules.people.application import Employee
from app.modules.timesheet.application.catalog import ShiftType

from ..adapters.orm import StatementKind
from .doc_render import (
    CODE_RE,
    PLACEHOLDER_HELP,
    build_sample_docx,
    build_values,
    delete_template,
    pdf_available,
    pdf_status,
    render_docx,
    save_template,
    scan_placeholders,
    template_path,
)
from .doc_templates import load_doc_templates

TEMPLATE_MAX_BYTES = 5 * 1024 * 1024

# встроенные виды без своего текста печатаются текстом из настроек объекта
FALLBACK_TEXT_KEY = {"vacation_paid": "vacation", "vacation_unpaid": "vacation_unpaid",
                     "day_off_hours": "day_off_hours", "time_off_request": "time_off_request"}


class KindIn(BaseModel):
    code: str
    name: str
    text: str = ""


class KindUpdate(BaseModel):
    name: str
    text: str = ""
    active: bool = True
    sort_order: int = 100


class RenderIn(BaseModel):
    """Данные заявления."""

    type: str
    employee_id: int
    date_from: str
    date_to: str
    format: str = "docx"        # docx | pdf
    from_time: str = ""         # «отпросился с 14:00…»
    until_time: str = ""        # «…до 16:00»
    hours: Optional[float] = None
    intervals: str = ""         # перечень интервалов одной строкой («с 14:00 до 16:00 (2 ч) и …»)
    reason: str = ""            # вид отсутствия из словаря («Отпуск», «Выходной за часы»…)
    note: str = ""              # примечание из ячейки графика (приказ, причина)


def _kind(db: Session, code: str) -> StatementKind:
    kind = db.scalar(select(StatementKind).where(StatementKind.code == code))
    if not kind:
        raise Validation(f"Неизвестный вид заявления: {code}")
    return kind


def _kind_by_id(db: Session, kind_id: int) -> StatementKind:
    kind = db.get(StatementKind, kind_id)
    if not kind:
        raise NotFound("Вид заявления не найден")
    return kind


def kind_dict(kind: StatementKind) -> dict:
    path = template_path(kind.code)
    return {"id": kind.id, "code": kind.code, "name": kind.name, "text": kind.text,
            "builtin": bool(kind.builtin), "active": bool(kind.active), "sort_order": kind.sort_order,
            "template": {"uploaded": path is not None, "filename": path.name if path else None,
                         "size": path.stat().st_size if path else 0,
                         "placeholders": sorted(scan_placeholders(path)) if path else []}}


# ─────────────────────────── виды заявлений ───────────────────────────

def kinds_view(db: Session) -> dict:
    """Виды заявлений с бланками, справка по плейсхолдерам и доступность PDF."""
    kinds = db.scalars(select(StatementKind).order_by(StatementKind.sort_order, StatementKind.name)).all()
    return {"kinds": [kind_dict(k) for k in kinds], "placeholders": PLACEHOLDER_HELP,
            "pdf_available": pdf_available(), "pdf": pdf_status()}


@transactional
def create_kind(db: Session, principal: Principal, data: KindIn) -> dict:
    code = data.code.strip().lower()
    if not CODE_RE.match(code):
        raise Validation("Код вида: строчная латиница, цифры и «_», 2–40 символов, "
                         "начинается с буквы (например mat_aid)")
    if not data.name.strip():
        raise Validation("Название вида заявления не может быть пустым")
    if db.scalar(select(StatementKind).where(StatementKind.code == code)):
        raise Conflict(f"Вид заявления с кодом «{code}» уже есть")
    kind = StatementKind(code=code, name=data.name.strip(), text=data.text)
    db.add(kind)
    audit(db, principal, "statement_kind_create", code, {"name": kind.name})
    db.flush()
    return kind_dict(kind)


@transactional
def update_kind(db: Session, principal: Principal, kind_id: int, data: KindUpdate) -> dict:
    kind = _kind_by_id(db, kind_id)
    if not data.name.strip():
        raise Validation("Название вида заявления не может быть пустым")
    kind.name = data.name.strip()
    kind.text = data.text
    kind.active = data.active
    kind.sort_order = data.sort_order
    audit(db, principal, "statement_kind_update", kind.code, {"name": kind.name})
    return kind_dict(kind)


@transactional
def delete_kind(db: Session, principal: Principal, kind_id: int) -> int:
    """Удалить вид заявления: у смен словаря, привязанных к нему, привязка очищается, бланк
    удаляется. Возвращает число очищенных смен."""
    kind = _kind_by_id(db, kind_id)
    shifts = db.scalars(select(ShiftType).where(ShiftType.doc_type == kind.code)).all()
    for shift in shifts:
        shift.doc_type = ""
    db.delete(kind)
    audit(db, principal, "statement_kind_delete", kind.code,
          {"name": kind.name, "shifts_cleared": [s.code for s in shifts]})
    db.flush()
    delete_template(kind.code)
    return len(shifts)


# ─────────────────────────── фирменные бланки ───────────────────────────

def sample(db: Session, code: str) -> tuple[bytes, str]:
    """Образец бланка с плейсхолдерами: его оформляют под фирменный стиль и загружают обратно."""
    kind = _kind(db, code)
    return build_sample_docx(kind.code, kind.text), f"sample_{kind.code}.docx"


@transactional
def upload_template(db: Session, principal: Principal, code: str, data: bytes, filename: Optional[str]) -> dict:
    """Загрузить фирменный бланк вида — файл .docx не больше 5 МБ."""
    _kind(db, code)
    if len(data) > TEMPLATE_MAX_BYTES:
        raise PayloadTooLarge("Файл больше 5 МБ")
    try:
        meta = save_template(code, data)         # проверяет, что это .docx, и только потом пишет файл
    except ValueError as exc:
        raise Validation(str(exc)) from exc
    audit(db, principal, "doc_template_upload", code, {"filename": filename})
    return meta


@transactional
def remove_template(db: Session, principal: Principal, code: str) -> bool:
    """Удалить бланк вида; вид снова печатается своим текстом. Возвращает, был ли бланк."""
    _kind(db, code)
    audit(db, principal, "doc_template_delete", code, {})
    db.flush()
    return delete_template(code)


# ─────────────────────────── формирование заявления ───────────────────────────

def _hours_between(from_time: str, until_time: str) -> float:
    """Часов между «с 14:00» и «до 16:00»; интервал через полночь тоже считается."""
    try:
        fh, fm = (int(x) for x in from_time.split(":"))
        th, tm = (int(x) for x in until_time.split(":"))
    except ValueError:
        return 0.0
    minutes = (th * 60 + tm) - (fh * 60 + fm)
    if minutes <= 0:
        minutes += 24 * 60
    return round(minutes / 60.0, 2)


def render(db: Session, principal: Principal, data: RenderIn) -> tuple[bytes, str, str]:
    """Сформировать заявление сотрудника. Возвращает содержимое, имя файла и тип содержимого.
    Формирование записывается в аудит и тогда, когда PDF собрать не удалось."""
    kind = _kind(db, data.type)
    employee = db.get(Employee, data.employee_id)
    if not employee:
        raise NotFound("Сотрудник не найден")
    try:
        first = dt.date.fromisoformat(data.date_from)
        last = dt.date.fromisoformat(data.date_to)
    except ValueError:
        raise Validation("Даты должны быть в формате ГГГГ-ММ-ДД") from None
    if last < first:
        raise Validation("Дата окончания раньше даты начала")

    settings = load_doc_templates(db)
    hours = data.hours
    if hours is None and data.from_time and data.until_time:
        hours = _hours_between(data.from_time, data.until_time)
    # {intervals}: готовый перечень отлучек либо один интервал из «с» и «до»
    intervals = data.intervals.strip()
    if not intervals and data.from_time and data.until_time:
        intervals = f"с {data.from_time} до {data.until_time} ({hours_text(hours or 0)} ч)"
    values = build_values(employee, first, last, extra={
        "company": settings["company"], "director": settings["director"],
        "from_time": data.from_time, "until_time": data.until_time,
        "hours": hours or 0, "reason": data.reason, "note": data.note, "intervals": intervals})
    fallback_key = FALLBACK_TEXT_KEY.get(kind.code)
    fallback = (kind.text or "").strip() or settings[fallback_key if fallback_key in settings else "vacation"]
    docx = render_docx(kind.code, values, fallback)

    with transaction(db):
        audit(db, principal, "doc_render", kind.code,
              {"employee": employee.full_name, "period": f"{first}..{last}", "format": data.format,
               "time": f"{data.from_time}-{data.until_time}" if data.from_time else ""})

    name = f"{kind.code}_{first.isoformat()}_{employee.id}"
    if data.format == "docx":
        return docx, f"{name}.docx", DOCX_MEDIA_TYPE
    pdf, how = docx_to_pdf(docx, f"{kind.code}_{employee.id}.pdf")
    if pdf is None:
        raise NotSupported(f"PDF собрать не удалось: {how}. Скачайте DOCX — он откроется "
                           "в Word/Pages/LibreOffice, из него можно напечатать напрямую.")
    return pdf, f"{name}.pdf", "application/pdf"
