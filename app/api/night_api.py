"""API ночного отчёта: области, чек-листы, ход смены, фото, выгрузка DOCX/PDF.

Доступ:
  * смотреть ночные отчёты и справочник областей — все авторизованные (в т.ч. батлеры);
  * вести проверку (взять область, отмечать пункты, закрывать) — любой сотрудник;
  * редактировать справочник областей/пунктов — только менеджер/администратор;
  * ручное закрытие/переоткрытие отчёта — супервайзер и выше.
"""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import Principal, audit, current_principal, require_manager, require_supervisor
from ..db import get_db
from ..deps import now_local
from ..models import (
    ChecklistItem,
    NightArea,
    NightAreaSection,
    NightCheckItem,
    NightInterception,
    NightReport,
    Setting,
)
from ..night import (
    current_shift_date,
    finalize_report,
    report_dict,
    section_dict,
    sync_reports,
)
from ..photos import photos_of, save_photo

router = APIRouter(prefix="/api/night", tags=["night"])

MAX_PHOTO_BYTES = 12 * 1024 * 1024   # 12 МБ на файл — храним оригиналы


# ─────────────────────────── входные модели ───────────────────────────

class AreaIn(BaseModel):
    name: str
    category: str = ""
    sort_order: int = 100
    active: bool = True


class ItemIn(BaseModel):
    text: str
    sort_order: int = 100
    active: bool = True


class AnswerIn(BaseModel):
    answer: str          # ok | bad | ''
    comment: str = ""


class InterceptionAck(BaseModel):
    ack: bool = False    # подтверждение перехвата области у другого батлера


class CloseSectionIn(BaseModel):
    force_unanswered: bool = False   # закрыть область с неотмеченными пунктами (ТЗ разрешает)


class CarCheckIn(BaseModel):
    found: bool = True
    location: str = ""
    canopy: bool = True
    charge: str = ""          # full | half | empty | ''
    on_charge: bool = False
    condition: str = "ok"     # ok | bad
    trash: bool = False
    clean: bool = True
    comment: str = ""


# ─────────────────────────── служебное ───────────────────────────

def _principal_name(pr: Principal) -> str:
    if pr.employee is not None:
        return pr.employee.display_name
    return pr.user.username


def _get_report(db: Session, report_id: int) -> NightReport:
    rep = db.get(NightReport, report_id)
    if rep is None:
        raise HTTPException(status_code=404, detail="Отчёт не найден")
    return rep


def _get_section(db: Session, section_id: int) -> NightAreaSection:
    sec = db.get(NightAreaSection, section_id)
    if sec is None:
        raise HTTPException(status_code=404, detail="Область не найдена")
    return sec


def _guard_open(rep: NightReport) -> None:
    if rep.status == "closed":
        raise HTTPException(status_code=409,
                            detail=f"Смена {rep.date.strftime('%d.%m.%Y')} закрыта — правки недоступны")


# ─────────────────────────── справочник областей ───────────────────────────

@router.get("/areas")
def list_areas(principal: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    """Справочник областей с пунктами (виден всем ролям, включая батлеров)."""
    out = []
    for area in db.scalars(select(NightArea).order_by(NightArea.sort_order, NightArea.id)):
        items = [{"id": it.id, "text": it.text, "sort_order": it.sort_order, "active": it.active}
                 for it in db.scalars(select(ChecklistItem)
                                      .where(ChecklistItem.area_id == area.id)
                                      .order_by(ChecklistItem.sort_order, ChecklistItem.id))]
        out.append({"id": area.id, "name": area.name, "category": area.category,
                    "sort_order": area.sort_order, "active": area.active,
                    "items": items, "items_total": len([i for i in items if i["active"]])})
    return {"areas": out, "can_edit": principal.role in ("admin", "manager")}


class AreaBulkIn(BaseModel):
    prefix: str
    start: int
    count: int
    category: str = ""


@router.post("/areas/bulk")
def create_areas_bulk(payload: AreaBulkIn, principal: Principal = Depends(require_manager),
                      db: Session = Depends(get_db)):
    """Массовое создание однотипных областей («Вилла VEG », 4001, 12 шт → 4001…4012)."""
    if payload.count < 1 or payload.count > 200:
        raise HTTPException(status_code=400, detail="Количество должно быть от 1 до 200")
    created = []
    for n in range(payload.start, payload.start + payload.count):
        name = f"{payload.prefix}{n}".strip()
        if db.scalar(select(NightArea).where(NightArea.name == name)):
            continue
        area = NightArea(name=name, category=payload.category, sort_order=n % 1000 + 100)
        db.add(area)
        db.flush()
        created.append(area.id)
    audit(db, principal, "night_areas_bulk", f"created:{len(created)}", payload.model_dump())
    db.commit()
    return {"created": len(created)}


@router.post("/areas")
def create_area(payload: AreaIn, principal: Principal = Depends(require_manager),
                db: Session = Depends(get_db)):
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Введите название области")
    if db.scalar(select(NightArea).where(NightArea.name == name)):
        raise HTTPException(status_code=409, detail="Такая область уже есть")
    area = NightArea(name=name, category=payload.category.strip(), sort_order=payload.sort_order,
                     active=payload.active)
    db.add(area)
    db.flush()
    audit(db, principal, "night_area_create", f"area:{area.id}", {"name": name})
    db.commit()
    return {"id": area.id}


@router.put("/areas/{area_id}")
def update_area(area_id: int, payload: AreaIn, principal: Principal = Depends(require_manager),
                db: Session = Depends(get_db)):
    area = db.get(NightArea, area_id)
    if area is None:
        raise HTTPException(status_code=404, detail="Область не найдена")
    old = {"name": area.name, "category": area.category, "active": area.active}
    area.name = payload.name.strip() or area.name
    area.category = payload.category.strip()
    area.sort_order = payload.sort_order
    area.active = payload.active
    audit(db, principal, "night_area_update", f"area:{area.id}", {"old": old, "new": payload.model_dump()})
    db.commit()
    return {"ok": True}


@router.delete("/areas/{area_id}")
def delete_area(area_id: int, principal: Principal = Depends(require_manager),
                db: Session = Depends(get_db)):
    """Удаление мягкое: активные отчёты пересоздаются со свежим снимком, история остаётся."""
    area = db.get(NightArea, area_id)
    if area is None:
        raise HTTPException(status_code=404, detail="Область не найдена")
    touched = 0
    for rep in db.scalars(select(NightReport).where(NightReport.status == "open")):
        sec = db.scalar(select(NightAreaSection).where(NightAreaSection.report_id == rep.id,
                                                       NightAreaSection.area_id == area_id))
        if sec is not None:
            db.delete(sec)
            touched += 1
    area.active = False
    audit(db, principal, "night_area_delete", f"area:{area.id}", {"sections_removed": touched})
    db.commit()
    return {"ok": True, "sections_removed": touched}


@router.post("/areas/{area_id}/items")
def add_item(area_id: int, payload: ItemIn, principal: Principal = Depends(require_manager),
             db: Session = Depends(get_db)):
    area = db.get(NightArea, area_id)
    if area is None:
        raise HTTPException(status_code=404, detail="Область не найдена")
    text = payload.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Введите текст пункта")
    item = ChecklistItem(area_id=area.id, text=text[:300], sort_order=payload.sort_order,
                         active=payload.active)
    db.add(item)
    db.flush()
    # добавленный пункт попадает только в ещё НЕ начатые открытые области
    added = 0
    for sec in db.scalars(select(NightAreaSection)
                          .join(NightReport, NightReport.id == NightAreaSection.report_id)
                          .where(NightReport.status == "open", NightAreaSection.area_id == area_id,
                                 NightAreaSection.status == "free")):
        db.add(NightCheckItem(section_id=sec.id, item_id=item.id, text=item.text,
                              sort_order=item.sort_order))
        snap = json.loads(sec.snapshot_json or "[]")
        snap.append({"id": item.id, "text": item.text})
        sec.snapshot_json = json.dumps(snap, ensure_ascii=False)
        added += 1
    audit(db, principal, "night_item_create", f"item:{item.id}", {"area": area.name, "added_to": added})
    db.commit()
    return {"id": item.id, "added_to_open_sections": added}


@router.put("/items/{item_id}")
def update_item(item_id: int, payload: ItemIn, principal: Principal = Depends(require_manager),
                db: Session = Depends(get_db)):
    item = db.get(ChecklistItem, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Пункт не найден")
    old_text = item.text
    item.text = payload.text.strip()[:300] or item.text
    item.sort_order = payload.sort_order
    item.active = payload.active
    # обновляем текст/порядок в ещё открытых (незавершённых) снимках
    for ni in db.scalars(select(NightCheckItem)
                         .join(NightAreaSection, NightAreaSection.id == NightCheckItem.section_id)
                         .join(NightReport, NightReport.id == NightAreaSection.report_id)
                         .where(NightCheckItem.item_id == item.id, NightReport.status == "open",
                                NightAreaSection.status != "done")):
        ni.text = item.text
        ni.sort_order = item.sort_order
        if not item.active and not ni.answer:
            # выключенный пункт без ответа убираем из незакрытой области
            snap = json.loads(ni.section.snapshot_json or "[]") if ni.section else []
            ni.section.snapshot_json = json.dumps(
                [x for x in snap if x.get("id") != item.id], ensure_ascii=False)
            db.delete(ni)
    audit(db, principal, "night_item_update", f"item:{item.id}",
          {"text": old_text, **payload.model_dump()})
    db.commit()
    return {"ok": True}


@router.delete("/items/{item_id}")
def delete_item(item_id: int, principal: Principal = Depends(require_manager),
                db: Session = Depends(get_db)):
    """Мягкое удаление: в незакрытых областях пункт исчезает, в закрытых остаётся навечно."""
    item = db.get(ChecklistItem, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Пункт не найден")
    item.active = False
    removed = 0
    for ni in db.scalars(select(NightCheckItem)
                         .join(NightAreaSection, NightAreaSection.id == NightCheckItem.section_id)
                         .join(NightReport, NightReport.id == NightAreaSection.report_id)
                         .where(NightCheckItem.item_id == item.id, NightReport.status == "open",
                                NightAreaSection.status != "done", NightCheckItem.answer == "")):
        db.delete(ni)
        removed += 1
    audit(db, principal, "night_item_delete", f"item:{item_id}", {"removed_from_open": removed})
    db.commit()
    return {"ok": True, "removed_from_open": removed}


# ─────────────────────────── ход смены ───────────────────────────

@router.get("/today")
def today_report(principal: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    """Актуальный отчёт текущей ночной смены (создаёт, если пора; закрывает наступившие)."""
    sync_reports(db)
    shift_d = current_shift_date()
    rep = db.scalar(select(NightReport).where(NightReport.date == shift_d))
    if rep is None:
        # после исправления ensure_report это возможно только до начала смены (до 20:00)
        return {"available": False, "shift_date": shift_d.isoformat(),
                "note": f"Ночная смена {shift_d.strftime('%d.%m.%Y')} ещё не началась — "
                        f"отчёт появится в 20:00. Прошлые смены — в «Архиве»."}
    return {"available": True, "report": _report_payload(db, rep)}


@router.get("/reports")
def list_reports(limit: int = 60, principal: Principal = Depends(current_principal),
                 db: Session = Depends(get_db)):
    """Архив ночных отчётов (супервайзер и выше): список с итогами."""
    sync_reports(db)
    out = []
    for rep in db.scalars(select(NightReport).order_by(NightReport.date.desc()).limit(min(limit, 365))):
        d = report_dict(rep, with_items=False)
        out.append(d)
    return {"reports": out}


@router.get("/reports/{report_id}")
def get_report(report_id: int, principal: Principal = Depends(current_principal),
               db: Session = Depends(get_db)):
    rep = _get_report(db, report_id)
    return {"report": _report_payload(db, rep)}


def _report_payload(db: Session, rep: NightReport) -> dict:
    """Отчёт + снимок обхода каров/перехватов + фото к пунктам (для экрана хода смены)."""
    data = report_dict(rep, db=db)
    item_ids = [i["id"] for s in data["areas"] for i in s.get("items", [])]
    pmap = photos_of(db, "night_item", item_ids) if item_ids else {}
    for s in data["areas"]:
        for it in s.get("items", []):
            it["photos"] = pmap.get(it["id"], [])
    return data


@router.post("/sections/{section_id}/take")
def take_section(section_id: int, payload: InterceptionAck,
                 principal: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    """Взять область в работу. Если её уже ведёт другой — предупреждаем и пишем перехват."""
    sec = _get_section(db, section_id)
    rep = _get_report(db, sec.report_id)
    _guard_open(rep)
    me = principal.user.id
    warning = None
    if sec.status == "taken" and sec.taken_by == me:
        return {"ok": True, "section": section_dict(sec), "warning": None, "already": True}
    if sec.status == "taken" and sec.taken_by and sec.taken_by != me:
        if not payload.ack:
            raise HTTPException(status_code=409, detail={
                "interception": True,
                "message": f"Эту область уже проверяет {sec.taken_by_name} "
                           f"(с {sec.taken_at:%H:%M}). Продолжить? Отметка перейдёт вам."})
        db.add(NightInterception(report_id=rep.id, section_id=sec.id,
                                 from_user_id=sec.taken_by, from_user_name=sec.taken_by_name,
                                 to_user_id=me, to_user_name=_principal_name(principal)))
        warning = f"Вы перехватили область у {sec.taken_by_name}"
    if sec.status == "done":
        # по ТЗ область ведёт один человек: закрыть её может кто угодно, а переоткрыть —
        # только тот, кто закрыл (или супервайзер и выше)
        if principal.user.id != sec.closed_by and principal.role not in ("supervisor", "manager", "admin"):
            raise HTTPException(status_code=409,
                                detail=f"Область закрыта в {sec.closed_at:%H:%M} — переоткрыть может "
                                       f"тот, кто её закрыл, или супервайзер")
        sec.status = "taken"
        sec.closed_at = None
        warning = "Область переоткрыта"
    sec.status = "taken"
    sec.taken_by = me
    sec.taken_by_name = _principal_name(principal)
    sec.taken_at = now_local()
    audit(db, principal, "night_section_take", f"section:{sec.id}",
          {"area": sec.name, "intercepted": bool(warning and "перехват" in warning)})
    db.commit()
    return {"ok": True, "section": section_dict(sec), "warning": warning}


@router.post("/sections/{section_id}/close")
def close_section(section_id: int, payload: CloseSectionIn | None = None,
                  principal: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    """Завершить проверку области.

    По ТЗ закрыть можно и с незаполненными пунктами (останутся «не отмечено») —
    но только после подтверждения; все пункты закрыты — закрываем сразу."""
    sec = _get_section(db, section_id)
    rep = _get_report(db, sec.report_id)
    _guard_open(rep)
    unanswered = [i for i in sec.items if not i.answer]
    force = bool(payload and payload.force_unanswered)
    if unanswered and not force:
        raise HTTPException(status_code=409, detail={
            "unanswered": len(unanswered),
            "message": f"Не отмечено пунктов: {len(unanswered)}. "
                       f"Они останутся как «не отмечено». Закрыть всё равно?"})
    sec.status = "done"
    sec.closed_at = now_local()
    sec.closed_by = principal.user.id
    audit(db, principal, "night_section_close", f"section:{sec.id}",
          {"area": sec.name, "unanswered": len(unanswered)})
    db.commit()
    return {"ok": True, "section": section_dict(sec)}


@router.post("/sections/{section_id}/reopen")
def reopen_section(section_id: int, principal: Principal = Depends(require_supervisor),
                   db: Session = Depends(get_db)):
    sec = _get_section(db, section_id)
    rep = _get_report(db, sec.report_id)
    _guard_open(rep)
    sec.status = "taken"
    sec.closed_at = None
    db.commit()
    return {"ok": True, "section": section_dict(sec)}


@router.put("/items/{item_id}/answer")
def answer_item(item_id: int, payload: AnswerIn, principal: Principal = Depends(current_principal),
                db: Session = Depends(get_db)):
    """Отметить пункт: ОК / Не ОК (+ комментарий). Перезапись — last write wins."""
    ni = db.get(NightCheckItem, item_id)
    if ni is None:
        raise HTTPException(status_code=404, detail="Пункт не найден")
    sec = _get_section(db, ni.section_id)
    rep = _get_report(db, sec.report_id)
    _guard_open(rep)
    if payload.answer not in ("ok", "bad", ""):
        raise HTTPException(status_code=400, detail="Неизвестный ответ")
    ni.answer = payload.answer
    ni.comment = payload.comment[:2000]
    ni.answered_by = principal.user.id
    ni.answered_by_name = _principal_name(principal)
    ni.answered_at = now_local()
    if sec.status == "free":       # отметка без «взять в работу» тоже закрепляет область
        sec.status = "taken"
        sec.taken_by = principal.user.id
        sec.taken_by_name = _principal_name(principal)
        sec.taken_at = now_local()
    db.commit()
    return {"ok": True, "item": {"id": ni.id, "answer": ni.answer, "comment": ni.comment}}


@router.post("/items/{item_id}/photo")
async def add_item_photo(item_id: int, file: UploadFile = File(...),
                         principal: Principal = Depends(current_principal),
                         db: Session = Depends(get_db)):
    ni = db.get(NightCheckItem, item_id)
    if ni is None:
        raise HTTPException(status_code=404, detail="Пункт не найден")
    sec = _get_section(db, ni.section_id)
    rep = _get_report(db, sec.report_id)
    _guard_open(rep)
    blob = await file.read(MAX_PHOTO_BYTES + 1)
    if len(blob) > MAX_PHOTO_BYTES:
        raise HTTPException(status_code=413, detail="Файл больше 12 МБ")
    try:
        photo = save_photo(db, kind="night_item", ref_id=ni.id, filename=file.filename or "photo.jpg",
                           blob=blob, user_id=principal.user.id, user_name=_principal_name(principal))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    db.commit()
    return {"ok": True, "photo": {"id": photo.id, "url": f"/api/photos/{photo.id}/file"}}


# ─────────────────────────── отдача файлов фото ───────────────────────────

@router.get("/photos/{photo_id}/file", operation_id="photo_file_night_get")
@router.head("/photos/{photo_id}/file", operation_id="photo_file_night_head",
             include_in_schema=False)
def photo_file(photo_id: int, principal: Principal = Depends(current_principal),
               db: Session = Depends(get_db)):
    """Отдача оригинала фото — алиас канонического `/api/photos/{id}/file`.

    Маршрут сохранён для совместимости со старыми ссылками; реализация общая
    (см. app/api/photos_api.py), чтобы поведение не могло разъехаться."""
    from .photos_api import photo_file as _photo_file

    return _photo_file(photo_id, principal, db)


# ─────────────────────────── шаг «Проверка электрокаров» ───────────────────────────

def _cars_section(rep: NightReport) -> NightAreaSection:
    for s in rep.areas:
        if s.area_id is None and s.category == "cars":
            return s
    raise HTTPException(status_code=404, detail="Шаг «Проверка электрокаров» не найден в отчёте")


@router.get("/reports/{report_id}/cars")
def report_cars(report_id: int, principal: Principal = Depends(current_principal),
                db: Session = Depends(get_db)):
    """Состояние обхода электрокаров за смену (список каров + отметки)."""
    from ..cars import night_cars_state

    rep = _get_report(db, report_id)
    return night_cars_state(db, rep)


@router.post("/reports/{report_id}/cars/{car_id}/check")
def report_car_check(report_id: int, car_id: int, payload: CarCheckIn,
                     principal: Principal = Depends(current_principal),
                     db: Session = Depends(get_db)):
    """Отметить кар в ходе ночного обхода (перезапись — last write wins).

    Отметки пишутся в общую базу: состояние карточки кара обновляется.
    «Не ОК» и «кар не найден» идут в замечания супервайзеру; отсутствие тента —
    просто факт, в замечания не входит."""
    from sqlalchemy.exc import IntegrityError

    from ..cars import CarOpError, check_car_night
    from ..models import Car

    rep = _get_report(db, report_id)
    _guard_open(rep)
    car = db.get(Car, car_id)
    if car is None:
        raise HTTPException(status_code=404, detail="Кар не найден")
    sec = _cars_section(rep)
    try:
        res = check_car_night(db, rep, car, principal, found=payload.found,
                              location=payload.location, canopy=payload.canopy,
                              charge=payload.charge, on_charge=payload.on_charge,
                              condition=payload.condition, trash=payload.trash,
                              clean=payload.clean, comment=payload.comment)
    except CarOpError as e:
        raise HTTPException(status_code=409, detail=str(e))
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
                       principal: Principal = Depends(current_principal),
                       db: Session = Depends(get_db)):
    """Завершить шаг «Проверка электрокаров». Незакрытые кары — только после подтверждения."""
    from ..cars import CarOpError, finish_cars_step, night_cars_state

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
                 principal: Principal = Depends(require_supervisor),
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
    finalize_report(rep)
    rep.close_reason = "manual"
    audit(db, principal, "night_report_close", f"report:{rep.id}", {"result": rep.result})
    db.commit()
    return {"ok": True, "report": _report_payload(db, rep)}


@router.post("/reports/{report_id}/reopen")
def reopen_report(report_id: int, principal: Principal = Depends(require_supervisor),
                  db: Session = Depends(get_db)):
    rep = _get_report(db, report_id)
    rep.status = "open"
    rep.result = ""
    rep.closed_at = None
    rep.close_reason = ""
    audit(db, principal, "night_report_reopen", f"report:{rep.id}", {})
    db.commit()
    return {"ok": True, "report": _report_payload(db, rep)}


@router.delete("/photos/{photo_id}")
def delete_photo(photo_id: int, principal: Principal = Depends(current_principal),
                 db: Session = Depends(get_db)):
    """Удалить фото — алиас канонического `DELETE /api/photos/{id}`."""
    from .photos_api import photo_delete

    return photo_delete(photo_id, principal, db)


# ─────────────────────────── выгрузка ───────────────────────────

def _company(db: Session) -> str:
    s = db.get(Setting, "doc_company")
    return (s.value if s and s.value else "")


@router.get("/reports/{report_id}/export.docx")
def export_docx(report_id: int, principal: Principal = Depends(current_principal),
                db: Session = Depends(get_db)):
    from ..night_export import render_night_report_docx

    rep = _get_report(db, report_id)
    item_ids = [i.id for s in rep.areas for i in s.items]
    pmap = photos_of(db, "night_item", item_ids)
    docx = render_night_report_docx(db, rep.id, company=_company(db), photos_map=pmap)
    name = f"night-{rep.date.isoformat()}.docx"
    return Response(docx, media_type=(
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
        headers={"Content-Disposition": f'attachment; filename="{name}"'})


@router.get("/reports/{report_id}/export.pdf")
def export_pdf(report_id: int, principal: Principal = Depends(current_principal),
               db: Session = Depends(get_db)):
    from ..night_export import render_night_report_docx
    from ..pdf_render import docx_to_pdf

    rep = _get_report(db, report_id)
    item_ids = [i.id for s in rep.areas for i in s.items]
    pmap = photos_of(db, "night_item", item_ids)
    docx = render_night_report_docx(db, rep.id, company=_company(db), photos_map=pmap)
    pdf, err = docx_to_pdf(docx, filename=f"night-{rep.date.isoformat()}.pdf")
    if pdf is None:
        raise HTTPException(status_code=422, detail=err or "PDF недоступен на этом сервере")
    return Response(pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="night-{rep.date.isoformat()}.pdf"'})
