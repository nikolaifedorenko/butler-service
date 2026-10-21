"""API ночного отчёта: области, чек-листы, ход смены, фото, выгрузка DOCX/PDF.

Доступ:
  * смотреть ночные отчёты и справочник областей — все авторизованные (в т.ч. батлеры);
  * вести проверку (взять область, отмечать пункты, закрывать) — любой сотрудник;
  * редактировать справочник областей/пунктов — только менеджер/администратор;
  * ручное закрытие/переоткрытие отчёта — супервайзер и выше.
"""
from __future__ import annotations

import datetime as dt
import json
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.core.audit import audit
from app.core.auth import Principal, current_principal
from app.core.db import get_db
from app.core.media import (
    UploadRef,
    max_upload_bytes,
    photos_of,
    read_upload_streaming,
    resolve_photo_file,
    save_photo_ref,
)
from app.core.media import delete_photo as delete_photo_usecase
from app.core.permissions import has_perm, require_perm
from app.core.settings_store import Setting
from app.core.time import now_local
from app.modules.notify.application.catalog import ResponsibilityService

from ..adapters.orm import (
    ChecklistItem,
    ChecklistOverride,
    NightArea,
    NightAreaSection,
    NightCheckItem,
    NightInterception,
    NightReport,
    NightZone,
    ZoneChecklistItem,
)
from ..application.night import (
    SHIFT_START,
    current_shift_date,
    defects_of,
    effective_items,
    finalize_report,
    refresh_free_section,
    report_dict,
    section_dict,
    service_dict,
    services_map,
    zone_dict,
)

router = APIRouter(prefix="/api/night", tags=["night"])

# Лимиты размера медиа задаёт объект (photo_max_mb / video_max_mb) — см. photos.media_limits()


# ─────────────────────────── входные модели ───────────────────────────

class AreaIn(BaseModel):
    name: str
    category: str = ""
    zone_id: Optional[int] = None     # зона обхода (v2): чек-лист зоны действует для объекта
    sort_order: int = 100
    active: bool = True


class ZoneIn(BaseModel):
    name: str
    sort_order: int = 100
    active: bool = True


class ZoneItemIn(BaseModel):
    text: str
    sort_order: int = 100
    active: bool = True
    service_id: Optional[int] = None   # ответственная служба: кто получает недостаток


class OverrideIn(BaseModel):
    """Индивидуальная правка пункта шаблона зоны у конкретного объекта."""
    text: str = ""                       # своя формулировка ('' = как в шаблоне зоны)
    disabled: bool = False               # пункт у этого объекта не проверяется
    service_id: Optional[int] = None     # своя служба (None = как в шаблоне зоны)


class ItemIn(BaseModel):
    text: str
    sort_order: int = 100
    active: bool = True
    service_id: Optional[int] = None   # ответственная служба своего пункта объекта


class DispatchIn(BaseModel):
    """Ручная отправка недостатков службам (этап 5).

    mode="all" — всё, что ещё не отправлено; "selected" — только item_ids.
    service_ids сужает отправку до выбранных служб (кнопка «Отправить службе»).
    Автоотправки нет: ни закрытие объекта, ни закрытие смены ничего не шлют.
    """
    mode: str = "all"
    item_ids: list[int] = []
    service_ids: list[int] = []


class ServiceIn(BaseModel):
    """Ответственная служба: каналы доставки и получатели (этап 3).

    chat_ids — закрепление чатов из ОБЩЕГО каталога Telegram (получается в
    «Настройки → Чаты и Почта»), поэтому здесь только их числовые id.
    """
    name: str
    sort_order: int = 100
    active: bool = True
    use_telegram: bool = False
    use_email: bool = False
    email_to: str = ""
    email_copy: str = ""
    chat_ids: list[int] = []
    note: str = ""


class AnswerIn(BaseModel):
    answer: str          # ok | bad | ''
    comment: str = ""


class InterceptionAck(BaseModel):
    ack: bool = False    # подтверждение перехвата области у другого батлера


class CloseSectionIn(BaseModel):
    force_unanswered: bool = False   # закрыть область с неотмеченными пунктами (ТЗ разрешает)


# Отметка кара в ночном обходе приходит multipart-формой (поля + фото), как возврат
# кара в разделе «Электрокары» — поэтому входной Pydantic-модели здесь нет:
# поля объявлены в сигнатуре report_car_check() через Form(...).


# ─────────────────────────── служебное ───────────────────────────

def _principal_name(pr: Principal) -> str:
    name = pr.employee.display_name if pr.employee is not None else pr.user.username
    # «как сотрудник» — с пометкой, кто вошёл на самом деле (решение владельца В-3)
    return f"{pr.user.username} → как {name}" if pr.impersonated else name


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
def list_areas(principal: Principal = Depends(require_perm("night.view")), db: Session = Depends(get_db)):
    """Справочник областей с пунктами (виден всем ролям, включая батлеров)."""
    zones = {z.id: z.name for z in db.scalars(select(NightZone))}
    svc_names = services_map(db)
    out = []
    for area in db.scalars(select(NightArea).order_by(NightArea.sort_order, NightArea.id)):
        items = [{"id": it.id, "text": it.text, "sort_order": it.sort_order, "active": it.active,
                  "service_id": it.service_id,
                  "service_name": svc_names.get(it.service_id or 0, "")}
                 for it in db.scalars(select(ChecklistItem)
                                      .where(ChecklistItem.area_id == area.id)
                                      .order_by(ChecklistItem.sort_order, ChecklistItem.id))]
        zone_items = len(list(db.scalars(select(ZoneChecklistItem.id)
                                         .where(ZoneChecklistItem.zone_id == area.zone_id,
                                                ZoneChecklistItem.active.is_(True))))) \
            if area.zone_id else 0
        out.append({"id": area.id, "name": area.name, "category": area.category,
                    "zone_id": area.zone_id,
                    "zone_name": zones.get(area.zone_id, area.category or ""),
                    "sort_order": area.sort_order, "active": area.active,
                    "items": items, "items_total": len([i for i in items if i["active"]]),
                    # чек-лист объекта = шаблон зоны + свои пункты (v2)
                    "effective_total": zone_items + len([i for i in items if i["active"]])})
    return {"areas": out, "can_edit": has_perm(db, principal, "night.edit")}


class AreaBulkIn(BaseModel):
    prefix: str
    start: int
    count: int
    category: str = ""
    zone_id: Optional[int] = None


@router.post("/areas/bulk")
def create_areas_bulk(payload: AreaBulkIn, principal: Principal = Depends(require_perm("night.edit")),
                      db: Session = Depends(get_db)):
    """Массовое создание однотипных областей («Вилла VEG », 4001, 12 шт → 4001…4012)."""
    if payload.count < 1 or payload.count > 200:
        raise HTTPException(status_code=400, detail="Количество должно быть от 1 до 200")
    _check_zone(db, payload.zone_id)
    created = []
    for n in range(payload.start, payload.start + payload.count):
        name = f"{payload.prefix}{n}".strip()
        if db.scalar(select(NightArea).where(NightArea.name == name)):
            continue
        area = NightArea(name=name, category=payload.category, zone_id=payload.zone_id,
                         sort_order=n % 1000 + 100)
        db.add(area)
        db.flush()
        created.append(area.id)
    audit(db, principal, "night_areas_bulk", f"created:{len(created)}", payload.model_dump())
    db.commit()
    return {"created": len(created)}


@router.post("/areas")
def create_area(payload: AreaIn, principal: Principal = Depends(require_perm("night.edit")),
                db: Session = Depends(get_db)):
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Введите название области")
    if db.scalar(select(NightArea).where(NightArea.name == name)):
        raise HTTPException(status_code=409, detail="Такая область уже есть")
    _check_zone(db, payload.zone_id)
    area = NightArea(name=name, category=payload.category.strip(), zone_id=payload.zone_id,
                     sort_order=payload.sort_order, active=payload.active)
    db.add(area)
    db.flush()
    audit(db, principal, "night_area_create", f"area:{area.id}", {"name": name})
    db.commit()
    return {"id": area.id}


@router.put("/areas/{area_id}")
def update_area(area_id: int, payload: AreaIn, principal: Principal = Depends(require_perm("night.edit")),
                db: Session = Depends(get_db)):
    area = db.get(NightArea, area_id)
    if area is None:
        raise HTTPException(status_code=404, detail="Область не найдена")
    name = payload.name.strip()
    # уникальность имени при переименовании (P1-misc-3): раньше проверялась только
    # при создании — дубль имени падал в IntegrityError (500)
    if name and name != area.name and db.scalar(
            select(NightArea).where(NightArea.name == name, NightArea.id != area_id)):
        raise HTTPException(status_code=409, detail="Такая область уже есть")
    _check_zone(db, payload.zone_id)
    old = {"name": area.name, "category": area.category, "active": area.active,
           "zone_id": area.zone_id}
    area.name = name or area.name
    area.category = payload.category.strip()
    zone_changed = payload.zone_id != area.zone_id
    area.zone_id = payload.zone_id
    area.sort_order = payload.sort_order
    area.active = payload.active
    db.flush()
    # смена зоны меняет чек-лист объекта: пересобираем снимок в ещё не начатых сменах
    touched = refresh_free_section(db, area) if zone_changed else 0
    audit(db, principal, "night_area_update", f"area:{area.id}",
          {"old": old, "new": payload.model_dump(), "sections_refreshed": touched})
    db.commit()
    return {"ok": True, "sections_refreshed": touched}


@router.delete("/areas/{area_id}")
def delete_area(area_id: int, principal: Principal = Depends(require_perm("night.edit")),
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
def add_item(area_id: int, payload: ItemIn, principal: Principal = Depends(require_perm("night.edit")),
             db: Session = Depends(get_db)):
    area = db.get(NightArea, area_id)
    if area is None:
        raise HTTPException(status_code=404, detail="Область не найдена")
    text = payload.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Введите текст пункта")
    _check_service(db, payload.service_id)
    item = ChecklistItem(area_id=area.id, text=text[:300], sort_order=payload.sort_order,
                         active=payload.active, service_id=payload.service_id)
    db.add(item)
    db.flush()
    # добавленный пункт попадает только в ещё НЕ начатые открытые области
    svc_names = services_map(db)
    added = 0
    for sec in db.scalars(select(NightAreaSection)
                          .join(NightReport, NightReport.id == NightAreaSection.report_id)
                          .where(NightReport.status == "open", NightAreaSection.area_id == area_id,
                                 NightAreaSection.status == "free")):
        db.add(NightCheckItem(section_id=sec.id, item_id=item.id, text=item.text,
                              sort_order=item.sort_order, service_id=item.service_id,
                              service_name=svc_names.get(item.service_id or 0, "")))
        snap = json.loads(sec.snapshot_json or "[]")
        snap.append({"id": item.id, "src": "area", "text": item.text, "overridden": False,
                     "service_id": item.service_id,
                     "service_name": svc_names.get(item.service_id or 0, "")})
        sec.snapshot_json = json.dumps(snap, ensure_ascii=False)
        added += 1
    audit(db, principal, "night_item_create", f"item:{item.id}", {"area": area.name, "added_to": added})
    db.commit()
    return {"id": item.id, "added_to_open_sections": added}


@router.put("/items/{item_id}")
def update_item(item_id: int, payload: ItemIn, principal: Principal = Depends(require_perm("night.edit")),
                db: Session = Depends(get_db)):
    item = db.get(ChecklistItem, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Пункт не найден")
    old_text = item.text
    _check_service(db, payload.service_id)
    item.text = payload.text.strip()[:300] or item.text
    item.sort_order = payload.sort_order
    item.active = payload.active
    item.service_id = payload.service_id
    svc_names = services_map(db)
    # обновляем текст/порядок/службу в ещё открытых (незавершённых) снимках
    for ni in db.scalars(select(NightCheckItem)
                         .join(NightAreaSection, NightAreaSection.id == NightCheckItem.section_id)
                         .join(NightReport, NightReport.id == NightAreaSection.report_id)
                         .where(NightCheckItem.item_id == item.id, NightReport.status == "open",
                                NightAreaSection.status != "done")):
        ni.text = item.text
        ni.sort_order = item.sort_order
        ni.service_id = item.service_id
        ni.service_name = svc_names.get(item.service_id or 0, "")
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
def delete_item(item_id: int, principal: Principal = Depends(require_perm("night.edit")),
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


def _check_service(db: Session, service_id: Optional[int]) -> None:
    """Ответственная служба обязана существовать, иначе пункт останется без получателя."""
    if not service_id:
        return
    if db.get(ResponsibilityService, service_id) is None:
        raise HTTPException(status_code=400, detail="Ответственная служба не найдена")


def _check_zone(db: Session, zone_id: Optional[int]) -> None:
    """Зона обхода обязана существовать (ревью 20.10.2026, P1-misc-3): zone_id —
    внешний ключ области; битый id на PostgreSQL давал IntegrityError (500), а на
    SQLite (FK не включены) молча писал область-сироту."""
    if not zone_id:
        return
    if db.get(NightZone, zone_id) is None:
        raise HTTPException(status_code=400, detail="Зона обхода не найдена")


def _service_name_taken(db: Session, name: str, exclude_id: Optional[int] = None) -> bool:
    """Занято ли название службы (сравнение без учёта регистра).

    Сравниваем в Python, а не через SQL LOWER(): в SQLite lower() не работает с
    кириллицей, поэтому «Хозяйственная служба» и «ХОЗЯЙСТВЕННАЯ СЛУЖБА» там
    считались бы разными. Служб единицы — загрузка названий ничего не стоит.
    """
    want = name.strip().casefold()
    q = select(ResponsibilityService.id, ResponsibilityService.name)
    if exclude_id is not None:
        q = q.where(ResponsibilityService.id != exclude_id)
    return any(n.strip().casefold() == want for _, n in db.execute(q).all())


def _check_channels(payload: ServiceIn) -> None:
    """Каналы доставки: хотя бы один, и у каждого заполнен получатель."""
    if not payload.use_telegram and not payload.use_email:
        raise HTTPException(status_code=400,
                            detail="Выберите хотя бы один канал: чат Telegram и/или письмо")
    if payload.use_email and "@" not in (payload.email_to or ""):
        raise HTTPException(status_code=400,
                            detail="Укажите почтовый ящик службы (канал «письмо» включён)")


# ─────────────────────────── зоны обхода (v2) ───────────────────────────
# Первый уровень навигации: зона → объекты → чек-лист. Чек-лист задаётся НА ЗОНУ
# (ZoneChecklistItem), поэтому у десятков однотипных объектов он одинаковый;
# индивидуальные особенности объекта — ChecklistOverride (своя формулировка /
# отключить пункт), свой пункт одного объекта — ChecklistItem(area_id=…).

@router.get("/zones")
def list_zones(principal: Principal = Depends(require_perm("night.view")),
               db: Session = Depends(get_db)):
    """Справочник зон обхода: сколько в зоне объектов и пунктов шаблона.

    Видно всем ролям (зоны нужны батлерам для обхода). Счётчики — агрегатами,
    чтобы список не масштабировался запросами на зону.
    """
    areas_cnt = dict(db.execute(
        select(NightArea.zone_id, func.count(NightArea.id))
        .where(NightArea.active.is_(True), NightArea.zone_id.is_not(None))
        .group_by(NightArea.zone_id)).all())
    items_cnt = dict(db.execute(
        select(ZoneChecklistItem.zone_id, func.count(ZoneChecklistItem.id))
        .where(ZoneChecklistItem.active.is_(True))
        .group_by(ZoneChecklistItem.zone_id)).all())
    zones = [zone_dict(z, areas_total=areas_cnt.get(z.id, 0), items_total=items_cnt.get(z.id, 0))
             for z in db.scalars(select(NightZone).order_by(NightZone.sort_order, NightZone.id))]
    # can_edit — ключ night.edit из каталога прав (19.10.2026): раньше здесь была
    # роль is_manager; базово право есть у admin/manager/supervisor, поведение то же,
    # но теперь его можно выдать/снять грантом («Права доступа»)
    return {"zones": zones, "can_edit": has_perm(db, principal, "night.edit")}


@router.post("/zones")
def create_zone(payload: ZoneIn, principal: Principal = Depends(require_perm("night.edit")),
                db: Session = Depends(get_db)):
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Введите название зоны")
    if db.scalar(select(NightZone).where(NightZone.name == name)):
        raise HTTPException(status_code=409, detail="Такая зона уже есть")
    zone = NightZone(name=name[:160], sort_order=payload.sort_order, active=payload.active)
    db.add(zone)
    db.flush()
    audit(db, principal, "night_zone_create", f"zone:{zone.id}", payload.model_dump())
    db.commit()
    return zone_dict(zone)


@router.put("/zones/{zone_id}")
def update_zone(zone_id: int, payload: ZoneIn, principal: Principal = Depends(require_perm("night.edit")),
                db: Session = Depends(get_db)):
    zone = db.get(NightZone, zone_id)
    if zone is None:
        raise HTTPException(status_code=404, detail="Зона не найдена")
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Введите название зоны")
    dup = db.scalar(select(NightZone).where(NightZone.name == name, NightZone.id != zone_id))
    if dup is not None:
        raise HTTPException(status_code=409, detail="Такая зона уже есть")
    old = {"name": zone.name, "sort_order": zone.sort_order, "active": zone.active}
    zone.name = name[:160]
    zone.sort_order = payload.sort_order
    zone.active = payload.active
    # название зоны в открытых отчётах — снимок: обновляем только ещё не закрытые смены,
    # чтобы переименование зоны не переписывало историю
    for sec in db.scalars(select(NightAreaSection)
                          .join(NightReport, NightReport.id == NightAreaSection.report_id)
                          .where(NightAreaSection.zone_id == zone.id, NightReport.status == "open")):
        sec.zone_name = zone.name
    audit(db, principal, "night_zone_update", f"zone:{zone.id}", {"old": old, "new": payload.model_dump()})
    db.commit()
    return {"ok": True, "zone": zone_dict(zone)}


@router.delete("/zones/{zone_id}")
def delete_zone(zone_id: int, principal: Principal = Depends(require_perm("night.edit")),
                db: Session = Depends(get_db)):
    """Отключение зоны (мягкое): объекты и история смен сохраняются.

    Объекты зоны остаются на месте (у каждого свой признак active) — зона просто
    перестаёт предлагаться в справочниках. В уже созданных отчётах название зоны
    хранится снимком (night_area_sections.zone_name).
    """
    zone = db.get(NightZone, zone_id)
    if zone is None:
        raise HTTPException(status_code=404, detail="Зона не найдена")
    zone.active = False
    areas = len(list(db.scalars(select(NightArea.id).where(NightArea.zone_id == zone.id,
                                                           NightArea.active.is_(True)))))
    audit(db, principal, "night_zone_delete", f"zone:{zone_id}", {"areas_left": areas})
    db.commit()
    return {"ok": True, "areas_left": areas}


@router.get("/zones/{zone_id}/items")
def zone_items(zone_id: int, principal: Principal = Depends(require_perm("night.view")),
               db: Session = Depends(get_db)):
    """Шаблон чек-листа зоны + объекты зоны (для экрана настроек)."""
    zone = db.get(NightZone, zone_id)
    if zone is None:
        raise HTTPException(status_code=404, detail="Зона не найдена")
    areas = [{"id": a.id, "name": a.name, "active": bool(a.active)}
             for a in db.scalars(select(NightArea).where(NightArea.zone_id == zone_id)
                                 .order_by(NightArea.sort_order, NightArea.id))]
    area_ids = [a["id"] for a in areas]
    ovs = dict(db.execute(select(ChecklistOverride.zone_item_id, func.count(ChecklistOverride.id))
                          .where(ChecklistOverride.area_id.in_(area_ids))
                          .group_by(ChecklistOverride.zone_item_id)).all()) if area_ids else {}
    svc_names = services_map(db)
    items = []
    for i in db.scalars(select(ZoneChecklistItem).where(ZoneChecklistItem.zone_id == zone_id)
                        .order_by(ZoneChecklistItem.sort_order, ZoneChecklistItem.id)):
        items.append({"id": i.id, "text": i.text, "sort_order": i.sort_order,
                      "active": bool(i.active), "overrides": ovs.get(i.id, 0),
                      "service_id": i.service_id,
                      "service_name": svc_names.get(i.service_id or 0, "")})
    return {"zone": zone_dict(zone, areas_total=len(areas),
                              items_total=len([i for i in items if i["active"]])),
            "items": items, "areas": areas}


@router.post("/zones/{zone_id}/items")
def add_zone_item(zone_id: int, payload: ZoneItemIn,
                  principal: Principal = Depends(require_perm("night.edit")), db: Session = Depends(get_db)):
    """Пункт шаблона зоны: попадает в чек-листы ВСЕХ объектов зоны.

    В открытых сменах пункт добавляется только к ещё НЕ начатым объектам
    (status="free") — как у пунктов отдельного объекта: начатые не перекраиваем.
    """
    zone = db.get(NightZone, zone_id)
    if zone is None:
        raise HTTPException(status_code=404, detail="Зона не найдена")
    text = payload.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Введите текст пункта")
    _check_service(db, payload.service_id)
    item = ZoneChecklistItem(zone_id=zone.id, text=text[:300], sort_order=payload.sort_order,
                             active=payload.active, service_id=payload.service_id)
    db.add(item)
    db.flush()
    refreshed = 0
    for area in db.scalars(select(NightArea).where(NightArea.zone_id == zone.id,
                                                   NightArea.active.is_(True))):
        refreshed += refresh_free_section(db, area)
    audit(db, principal, "night_zone_item_create", f"zone:{zone.id}",
          {**payload.model_dump(), "sections_refreshed": refreshed})
    db.commit()
    return {"ok": True, "id": item.id, "sections_refreshed": refreshed}


def _remove_zone_item_from_open(db: Session, item: ZoneChecklistItem) -> int:
    """Убрать пункт шаблона из незакрытых областей (отмеченные не трогаем)."""
    removed = 0
    for ni in db.scalars(select(NightCheckItem)
                         .join(NightAreaSection, NightAreaSection.id == NightCheckItem.section_id)
                         .join(NightReport, NightReport.id == NightAreaSection.report_id)
                         .where(NightCheckItem.zone_item_id == item.id, NightReport.status == "open",
                                NightAreaSection.status != "done", NightCheckItem.answer == "")):
        snap = json.loads(ni.section.snapshot_json or "[]")
        ni.section.snapshot_json = json.dumps(
            [x for x in snap if not (x.get("src") == "zone" and x.get("id") == item.id)],
            ensure_ascii=False)
        db.delete(ni)
        removed += 1
    return removed


@router.put("/zone-items/{item_id}")
def update_zone_item(item_id: int, payload: ZoneItemIn,
                     principal: Principal = Depends(require_perm("night.edit")), db: Session = Depends(get_db)):
    """Правка пункта шаблона зоны: текст уезжает во все незакрытые снимки объектов зоны."""
    item = db.get(ZoneChecklistItem, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Пункт не найден")
    _check_service(db, payload.service_id)
    old_text = item.text
    item.text = payload.text.strip()[:300] or item.text
    item.sort_order = payload.sort_order
    item.active = payload.active
    item.service_id = payload.service_id
    svc_names = services_map(db)
    for ni in db.scalars(select(NightCheckItem)
                         .join(NightAreaSection, NightAreaSection.id == NightCheckItem.section_id)
                         .join(NightReport, NightReport.id == NightAreaSection.report_id)
                         .where(NightCheckItem.zone_item_id == item.id, NightReport.status == "open",
                                NightAreaSection.status != "done")):
        ni.text = item.text
        ni.sort_order = item.sort_order
        # служба пункта шаблона меняется и в незакрытых сменах; у объекта может быть
        # своя служба (ChecklistOverride) — её не переопределяем
        own = {o.zone_item_id for o in db.scalars(select(ChecklistOverride).where(
            ChecklistOverride.zone_item_id == item.id,
            ChecklistOverride.service_id.is_not(None)))}
        if ni.section.area_id not in own:
            ni.service_id = item.service_id
            ni.service_name = svc_names.get(item.service_id or 0, "")
    removed = _remove_zone_item_from_open(db, item) if not item.active else 0
    audit(db, principal, "night_zone_item_update", f"zone_item:{item.id}",
          {"old_text": old_text, **payload.model_dump(), "removed_from_open": removed})
    db.commit()
    return {"ok": True, "removed_from_open": removed}


@router.delete("/zone-items/{item_id}")
def delete_zone_item(item_id: int, principal: Principal = Depends(require_perm("night.edit")),
                     db: Session = Depends(get_db)):
    """Мягкое удаление пункта шаблона: в незакрытых сменах исчезает, в закрытых остаётся."""
    item = db.get(ZoneChecklistItem, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Пункт не найден")
    item.active = False
    removed = _remove_zone_item_from_open(db, item)
    audit(db, principal, "night_zone_item_delete", f"zone_item:{item_id}",
          {"removed_from_open": removed})
    db.commit()
    return {"ok": True, "removed_from_open": removed}


@router.get("/areas/{area_id}/checklist")
def area_checklist(area_id: int, principal: Principal = Depends(require_perm("night.view")),
                   db: Session = Depends(get_db)):
    """Чек-лист объекта для настроек: шаблон зоны с правками + свои пункты + итог."""
    area = db.get(NightArea, area_id)
    if area is None:
        raise HTTPException(status_code=404, detail="Область не найдена")
    zone = db.get(NightZone, area.zone_id) if area.zone_id else None
    ovs = {o.zone_item_id: o for o in db.scalars(select(ChecklistOverride)
                                                 .where(ChecklistOverride.area_id == area.id))}
    svc_names = services_map(db)
    zone_items = []
    if zone is not None:
        for i in db.scalars(select(ZoneChecklistItem)
                            .where(ZoneChecklistItem.zone_id == zone.id,
                                   ZoneChecklistItem.active.is_(True))
                            .order_by(ZoneChecklistItem.sort_order, ZoneChecklistItem.id)):
            ov = ovs.get(i.id)
            sid = ov.service_id if (ov and ov.service_id) else i.service_id
            zone_items.append({
                "id": i.id, "text": i.text, "sort_order": i.sort_order,
                "override_text": ov.text if ov else "", "disabled": bool(ov.disabled) if ov else False,
                "effective_text": (ov.text if ov and ov.text else i.text),
                "in_checklist": not (ov.disabled if ov else False),
                "service_id": i.service_id,
                "service_name": svc_names.get(i.service_id or 0, ""),
                "override_service_id": ov.service_id if ov else None,
                "override_service_name": svc_names.get(ov.service_id or 0, "") if ov else "",
                "effective_service_id": sid,
                "effective_service_name": svc_names.get(sid or 0, "")})
    own = [{"id": i.id, "text": i.text, "sort_order": i.sort_order, "active": bool(i.active),
            "service_id": i.service_id, "service_name": svc_names.get(i.service_id or 0, "")}
           for i in db.scalars(select(ChecklistItem)
                               .where(ChecklistItem.area_id == area.id, ChecklistItem.active.is_(True))
                               .order_by(ChecklistItem.sort_order, ChecklistItem.id))]
    return {"area": {"id": area.id, "name": area.name, "zone_id": area.zone_id,
                     "zone_name": zone.name if zone else (area.category or ""),
                     "active": bool(area.active)},
            "zone_items": zone_items, "own_items": own,
            "effective": effective_items(db, area)}


@router.put("/areas/{area_id}/overrides/{zone_item_id}")
def set_override(area_id: int, zone_item_id: int, payload: OverrideIn,
                 principal: Principal = Depends(require_perm("night.edit")), db: Session = Depends(get_db)):
    """Индивидуальная правка пункта шаблона зоны у объекта (своя формулировка / отключить).

    Пустая формулировка и снятое отключение означают «как в шаблоне зоны» — запись
    правки удаляется. Применяется к ещё НЕ начатым объектам в открытых сменах.
    """
    area = db.get(NightArea, area_id)
    if area is None:
        raise HTTPException(status_code=404, detail="Область не найдена")
    item = db.get(ZoneChecklistItem, zone_item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Пункт шаблона зоны не найден")
    if item.zone_id != area.zone_id:
        raise HTTPException(status_code=400,
                            detail="Пункт не из шаблона зоны этого объекта")
    _check_service(db, payload.service_id)
    text = payload.text.strip()[:300]
    ov = db.scalar(select(ChecklistOverride).where(ChecklistOverride.area_id == area.id,
                                                  ChecklistOverride.zone_item_id == item.id))
    # правка удаляется, только если объект снова во всём как шаблон зоны:
    # нет своей формулировки, пункт не отключён и служба не переопределена
    if not text and not payload.disabled and not payload.service_id:
        if ov is not None:
            db.delete(ov)
    elif ov is None:
        db.add(ChecklistOverride(area_id=area.id, zone_item_id=item.id, text=text,
                                 disabled=bool(payload.disabled), service_id=payload.service_id))
    else:
        ov.text = text
        ov.disabled = bool(payload.disabled)
        ov.service_id = payload.service_id
    db.flush()
    touched = refresh_free_section(db, area)
    audit(db, principal, "night_override_set", f"area:{area.id}",
          {"zone_item_id": item.id, "text": text, "disabled": bool(payload.disabled),
           "service_id": payload.service_id, "sections_refreshed": touched})
    db.commit()
    return {"ok": True, "sections_refreshed": touched, "effective": effective_items(db, area)}


@router.delete("/areas/{area_id}/overrides/{zone_item_id}")
def reset_override(area_id: int, zone_item_id: int,
                   principal: Principal = Depends(require_perm("night.edit")), db: Session = Depends(get_db)):
    """Сброс правки: пункт у объекта снова как в шаблоне зоны."""
    area = db.get(NightArea, area_id)
    if area is None:
        raise HTTPException(status_code=404, detail="Область не найдена")
    ov = db.scalar(select(ChecklistOverride).where(ChecklistOverride.area_id == area.id,
                                                  ChecklistOverride.zone_item_id == zone_item_id))
    if ov is not None:
        db.delete(ov)
        # сессия без autoflush: фиксируем удаление ДО пересчёта чек-листа,
        # иначе снимок пересоберётся по ещё не удалённой правке
        db.flush()
    touched = refresh_free_section(db, area) if ov is not None else 0
    audit(db, principal, "night_override_reset", f"area:{area.id}",
          {"zone_item_id": zone_item_id, "sections_refreshed": touched})
    db.commit()
    return {"ok": True, "sections_refreshed": touched}


# ─────────────────────── ответственные службы (этап 3) ───────────────────────
# Служба — получатель недостатков ночного обхода: закрепляется за пунктом шаблона
# зоны, у отдельного объекта переопределяется индивидуальной правкой. В отчёт
# попадает снимком (service_name), поэтому переименование не меняет закрытые смены.
# Здесь — только получатели и каналы; транспорт и учётные данные общие
# («Настройки → Чаты и Почта», этап 4).

@router.get("/services")
def list_services(principal: Principal = Depends(require_perm("night.view")),
                  db: Session = Depends(get_db)):
    """Справочник служб: каналы, получатели и сколько пунктов за каждой закреплено."""
    zone_counts = dict(db.execute(
        select(ZoneChecklistItem.service_id, func.count(ZoneChecklistItem.id))
        .where(ZoneChecklistItem.active.is_(True), ZoneChecklistItem.service_id.is_not(None))
        .group_by(ZoneChecklistItem.service_id)).all())
    own_counts = dict(db.execute(
        select(ChecklistItem.service_id, func.count(ChecklistItem.id))
        .where(ChecklistItem.active.is_(True), ChecklistItem.service_id.is_not(None))
        .group_by(ChecklistItem.service_id)).all())
    rows = [service_dict(s, items_total=zone_counts.get(s.id, 0) + own_counts.get(s.id, 0))
            for s in db.scalars(select(ResponsibilityService)
                                .order_by(ResponsibilityService.sort_order,
                                          ResponsibilityService.id))]
    return {"services": rows, "can_edit": has_perm(db, principal, "night.edit")}


@router.post("/services")
def create_service(payload: ServiceIn, principal: Principal = Depends(require_perm("night.edit")),
                   db: Session = Depends(get_db)):
    name = payload.name.strip()[:160]
    if not name:
        raise HTTPException(status_code=400, detail="Введите название службы")
    if _service_name_taken(db, name):
        raise HTTPException(status_code=409, detail="Служба с таким названием уже есть")
    _check_channels(payload)
    svc = ResponsibilityService(
        name=name, sort_order=payload.sort_order, active=payload.active,
        use_telegram=payload.use_telegram, use_email=payload.use_email,
        email_to=payload.email_to.strip()[:200], email_copy=payload.email_copy.strip()[:400],
        chat_ids=json.dumps(payload.chat_ids), note=payload.note.strip()[:300])
    db.add(svc)
    db.flush()
    audit(db, principal, "night_service_create", f"service:{svc.id}", payload.model_dump())
    db.commit()
    return {"ok": True, "id": svc.id, "service": service_dict(svc)}


@router.put("/services/{service_id}")
def update_service(service_id: int, payload: ServiceIn,
                   principal: Principal = Depends(require_perm("night.edit")),
                   db: Session = Depends(get_db)):
    """Правка службы: новое название уходит в незакрытые смены, в закрытых остаётся старое."""
    svc = db.get(ResponsibilityService, service_id)
    if svc is None:
        raise HTTPException(status_code=404, detail="Служба не найдена")
    name = payload.name.strip()[:160]
    if not name:
        raise HTTPException(status_code=400, detail="Введите название службы")
    if _service_name_taken(db, name, exclude_id=svc.id):
        raise HTTPException(status_code=409, detail="Служба с таким названием уже есть")
    _check_channels(payload)
    old = service_dict(svc)
    svc.name = name
    svc.sort_order = payload.sort_order
    svc.active = payload.active
    svc.use_telegram = payload.use_telegram
    svc.use_email = payload.use_email
    svc.email_to = payload.email_to.strip()[:200]
    svc.email_copy = payload.email_copy.strip()[:400]
    svc.chat_ids = json.dumps(payload.chat_ids)
    svc.note = payload.note.strip()[:300]
    db.flush()
    # снимок в незакрытых сменах обновляем (как у текста пункта шаблона зоны)
    updated = 0
    for ni in db.scalars(select(NightCheckItem)
                         .join(NightAreaSection, NightAreaSection.id == NightCheckItem.section_id)
                         .join(NightReport, NightReport.id == NightAreaSection.report_id)
                         .where(NightCheckItem.service_id == svc.id, NightReport.status == "open",
                                NightAreaSection.status != "done")):
        ni.service_name = svc.name
        updated += 1
    audit(db, principal, "night_service_update", f"service:{svc.id}",
          {"old": old, "new": service_dict(svc), "open_items_updated": updated})
    db.commit()
    return {"ok": True, "service": service_dict(svc), "open_items_updated": updated}


@router.delete("/services/{service_id}")
def delete_service(service_id: int, principal: Principal = Depends(require_perm("night.edit")),
                   db: Session = Depends(get_db)):
    """Отключение службы (не удаление): пункты и история закрытых смен остаются как были.

    Служба перестаёт предлагаться в справочнике и не участвует в новых отправках;
    закреплённые за ней пункты видны в ответе (items_total) — их стоит переназначить.
    """
    svc = db.get(ResponsibilityService, service_id)
    if svc is None:
        raise HTTPException(status_code=404, detail="Служба не найдена")
    svc.active = False
    items_total = db.scalar(select(func.count(ZoneChecklistItem.id))
                            .where(ZoneChecklistItem.service_id == svc.id,
                                   ZoneChecklistItem.active.is_(True))) or 0
    audit(db, principal, "night_service_delete", f"service:{service_id}",
          {"name": svc.name, "items_total": items_total})
    db.commit()
    return {"ok": True, "items_total": items_total}


# ─────────────────────────── ход смены ───────────────────────────

@router.get("/today")
def today_report(principal: Principal = Depends(require_perm("night.view")), db: Session = Depends(get_db)):
    """Актуальный отчёт текущей ночной смены.

    GET без побочных записей (ревью 20.10.2026, P1): обслуживание — досоздание
    наступивших смен и автозакрытие в 08:00 — выполняет фоновая синхронизация
    (bootstrap/night_sync.py, период settings.night_sync_seconds) и стартовый
    прогон init_db(), а не каждый запрос раздела."""
    shift_d = current_shift_date()
    rep = db.scalar(select(NightReport).where(NightReport.date == shift_d))
    if rep is None:
        # до 20:00 смена действительно ещё не началась; после — отчёт вот-вот
        # создаст фоновый раунд (или стартовый прогон, если сервер только поднялся)
        if now_local() < dt.datetime.combine(shift_d, SHIFT_START):
            note = (f"Ночная смена {shift_d.strftime('%d.%m.%Y')} ещё не началась — "
                    f"отчёт появится в 20:00. Прошлые смены — в «Архиве».")
        else:
            note = (f"Ночная смена {shift_d.strftime('%d.%m.%Y')} началась — отчёт создаётся; "
                    f"обновите страницу через минуту. Прошлые смены — в «Архиве».")
        return {"available": False, "shift_date": shift_d.isoformat(), "note": note}
    return {"available": True, "report": _report_payload(db, rep)}


@router.get("/reports")
def list_reports(limit: int = 60, principal: Principal = Depends(require_perm("night.view")),
                 db: Session = Depends(get_db)):
    """Архив ночных отчётов (супервайзер и выше): список с итогами (чистое чтение)."""
    out = []
    # PERF-01: области и пункты — тремя запросами на весь архив, а не по запросу на отчёт и область
    q = (select(NightReport)
         .options(selectinload(NightReport.areas).selectinload(NightAreaSection.items))
         .order_by(NightReport.date.desc()).limit(min(limit, 365)))
    for rep in db.scalars(q):
        d = report_dict(rep, with_items=False)
        out.append(d)
    return {"reports": out}


@router.get("/reports/{report_id}")
def get_report(report_id: int, principal: Principal = Depends(require_perm("night.view")),
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
                 principal: Principal = Depends(require_perm("night.view")), db: Session = Depends(get_db)):
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
                  principal: Principal = Depends(require_perm("night.view")), db: Session = Depends(get_db)):
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
def reopen_section(section_id: int, principal: Principal = Depends(require_perm("night.close")),
                   db: Session = Depends(get_db)):
    sec = _get_section(db, section_id)
    rep = _get_report(db, sec.report_id)
    _guard_open(rep)
    sec.status = "taken"
    sec.closed_at = None
    audit(db, principal, "night_section_reopen", f"section:{section_id}")
    db.commit()
    return {"ok": True, "section": section_dict(sec)}


@router.put("/items/{item_id}/answer")
def answer_item(item_id: int, payload: AnswerIn, principal: Principal = Depends(require_perm("night.view")),
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
    audit(db, principal, "night_item_answer", f"item:{item_id}",
          {"answer": ni.answer, "section_id": sec.id})
    db.commit()
    return {"ok": True, "item": {"id": ni.id, "answer": ni.answer, "comment": ni.comment}}


@router.post("/items/{item_id}/photo")
def add_item_photo(item_id: int, file: UploadFile = File(...),
                   principal: Principal = Depends(require_perm("night.view")),
                   db: Session = Depends(get_db)):
    ni = db.get(NightCheckItem, item_id)
    if ni is None:
        raise HTTPException(status_code=404, detail="Пункт не найден")
    sec = _get_section(db, ni.section_id)
    rep = _get_report(db, sec.report_id)
    _guard_open(rep)
    limit = max_upload_bytes(db)
    # потоковая загрузка: файл идёт на диск чанками, не в память (P1 20.10.2026)
    ref = read_upload_streaming(file, limit)
    try:
        photo = save_photo_ref(db, kind="night_item", ref_id=ni.id, ref=ref,
                               user_id=principal.user.id, user_name=_principal_name(principal))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        ref.discard()   # после save_photo_ref файла уже нет (перенесён/удалён) — missing_ok
    db.commit()
    return {"ok": True, "photo": {"id": photo.id, "url": f"/api/photos/{photo.id}/file",
                                  "media_type": photo.media_type or "photo"}}


# ─────────────── недостатки смены и отправка службам (этап 5) ───────────────
# Экран консолидированной отправки: «Не ОК» и «Не проверено» группируются по
# ответственным службам, отправляются вручную (всё или выбранное), отправленное
# помечается. Исправленное ПОСЛЕ отправки повторно не уходит и не отзывается.
# Отправка — право night.dispatch (В-5), по умолчанию у всех ролей.

@router.get("/reports/{report_id}/defects")
def report_defects(report_id: int, principal: Principal = Depends(require_perm("night.view")),
                   db: Session = Depends(get_db)):
    """Недостатки смены: позиции, группы по службам, журнал, шаблон сообщения."""
    from ..application.night_notify import defects_payload

    rep = _get_report(db, report_id)
    return defects_payload(db, rep)


@router.post("/reports/{report_id}/dispatch", dependencies=[Depends(require_perm("night.view"))])
def dispatch_report(report_id: int, payload: DispatchIn,
                    principal: Principal = Depends(require_perm("night.dispatch")),
                    db: Session = Depends(get_db)):
    """Отправить недостатки службам: всё скопом или выбранное (только вручную)."""
    from ..application.night_notify import dispatch_defects

    rep = _get_report(db, report_id)
    res = dispatch_defects(db, rep, principal, mode=payload.mode,
                           item_ids=payload.item_ids, service_ids=payload.service_ids)
    return res


@router.get("/reports/{report_id}/dispatches")
def report_dispatches(report_id: int, limit: int = 50,
                      principal: Principal = Depends(require_perm("night.view")),
                      db: Session = Depends(get_db)):
    """Журнал отправок смены — строки общего журнала раздела «Ночной отчёт»."""
    from ..application.night_notify import report_journal

    rep = _get_report(db, report_id)
    return {"dispatches": report_journal(db, rep, limit=limit)}


@router.post("/reports/{report_id}/defects/preview")
def preview_defects(report_id: int, payload: DispatchIn,
                    principal: Principal = Depends(require_perm("night.view")),
                    db: Session = Depends(get_db)):
    """Предпросмотр сообщений: что именно уйдёт каждой службе (без отправки)."""
    from app.modules.notify.application.recipients import group_by_service

    from ..application.night_notify import DOMAIN, preview_message

    rep = _get_report(db, report_id)
    data = defects_of(db, rep)
    rows = [d for d in data["items"] if d["sendable"]]
    if payload.mode == "selected":
        wanted = {int(i) for i in payload.item_ids}
        rows = [d for d in rows if d["id"] in wanted]
    if payload.service_ids:
        allowed = {int(i) for i in payload.service_ids}
        rows = [d for d in rows if d.get("service_id") in allowed]
    out = []
    for group in group_by_service(db, rows):
        if not [d for d in group["defects"] if d["sendable"]]:
            continue
        out.append({"service_id": group["service_id"], "service_name": group["service_name"],
                    "channels": group["channels"], "problems": group["problems"],
                    "defects": group["counts"]["sendable"],
                    "message": preview_message(db, rep, group, principal.name)})
    return {"ok": True, "messages": out, "domain": DOMAIN}


# ─────────────────────────── отдача файлов фото ───────────────────────────

@router.get("/photos/{photo_id}/file", operation_id="photo_file_night_get")
@router.head("/photos/{photo_id}/file", operation_id="photo_file_night_head",
             include_in_schema=False)
def photo_file(photo_id: int, principal: Principal = Depends(current_principal),
               db: Session = Depends(get_db)):
    """Отдача оригинала фото — алиас канонического `/api/photos/{id}/file`.

    Маршрут сохранён для совместимости со старыми ссылками; реализация общая
    (см. app/api/photos_api.py), чтобы поведение не могло разъехаться."""
    p, path, mime = resolve_photo_file(db, photo_id, principal)
    return FileResponse(str(path), media_type=mime or "application/octet-stream",
                        filename=p.filename or None,
                        headers={"Cache-Control": "private, max-age=86400"})


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


@router.delete("/photos/{photo_id}")
def delete_photo(photo_id: int, principal: Principal = Depends(current_principal),
                 db: Session = Depends(get_db)):
    """Удалить фото — алиас канонического `DELETE /api/photos/{id}`."""
    delete_photo_usecase(db, principal, photo_id)
    return {"ok": True}


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
