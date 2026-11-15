"""Справочники ночного обхода: зоны, объекты, пункты чек-листа, особенности объектов, службы.

Навигация обхода: зона → объекты → чек-лист. Чек-лист задаётся на зону
(``ZoneChecklistItem``), поэтому у однотипных объектов он общий. Особенность объекта —
``ChecklistOverride`` (своя формулировка, своя служба, отключённый пункт), свой пункт одного
объекта — ``ChecklistItem``. Служба — получатель недостатков по пункту.

Отчёт смены хранит справочник снимком. Правка справочника меняет снимок только в открытых
сменах: объект, который ещё не взят в работу, пересобирается целиком; у начатого меняются
текст и служба пунктов, а пункты с отметками не удаляются. Закрытые смены не меняются.
Каждая операция — одна транзакция вместе с записью аудита.
"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.audit import audit
from app.core.auth import Principal
from app.core.db import transactional
from app.core.errors import Conflict, NotFound, Rejected
from app.core.media import delete_photo_files
from app.core.permissions import has_perm
from app.modules.notify.application.catalog import ResponsibilityService

from ..adapters.orm import (
    ChecklistItem,
    ChecklistOverride,
    NightArea,
    NightAreaSection,
    NightCheckItem,
    NightReport,
    NightZone,
    ZoneChecklistItem,
)
from .night import effective_items, refresh_free_section, service_dict, services_map, zone_dict

# ─────────────────────────── данные операций ───────────────────────────


class AreaIn(BaseModel):
    name: str
    category: str = ""
    zone_id: Optional[int] = None     # зона обхода: её чек-лист действует для объекта
    sort_order: int = 100
    active: bool = True


class AreaBulkIn(BaseModel):
    """Однотипные объекты подряд: «Вилла », 4001, 12 штук → «Вилла 4001» … «Вилла 4012»."""

    prefix: str
    start: int
    count: int
    category: str = ""
    zone_id: Optional[int] = None


class ZoneIn(BaseModel):
    name: str
    sort_order: int = 100
    active: bool = True


class ItemIn(BaseModel):
    """Пункт чек-листа — шаблона зоны или свой пункт объекта."""

    text: str
    sort_order: int = 100
    active: bool = True
    service_id: Optional[int] = None   # ответственная служба: кто получает недостаток


class OverrideIn(BaseModel):
    """Особенность объекта для пункта шаблона зоны."""

    text: str = ""                       # своя формулировка ('' — как в шаблоне зоны)
    disabled: bool = False               # пункт у этого объекта не проверяется
    service_id: Optional[int] = None     # своя служба (None — как в шаблоне зоны)


class ServiceIn(BaseModel):
    """Ответственная служба: каналы доставки и получатели.

    chat_ids — чаты из общего каталога Telegram («Настройки → Чаты и Почта»), здесь только id.
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


# ─────────────────────────── общие проверки ───────────────────────────

def _area(db: Session, area_id: int) -> NightArea:
    area = db.get(NightArea, area_id)
    if area is None:
        raise NotFound("Область не найдена")
    return area


def _zone(db: Session, zone_id: int) -> NightZone:
    zone = db.get(NightZone, zone_id)
    if zone is None:
        raise NotFound("Зона не найдена")
    return zone


def _check_service(db: Session, service_id: Optional[int]) -> None:
    """Служба пункта обязана существовать, иначе недостаток останется без получателя."""
    if service_id and db.get(ResponsibilityService, service_id) is None:
        raise Rejected("Ответственная служба не найдена")


def _check_zone(db: Session, zone_id: Optional[int]) -> None:
    if zone_id and db.get(NightZone, zone_id) is None:
        raise Rejected("Зона обхода не найдена")


def _open_items(*where):
    """Пункты отчётов открытых смен в объектах, которые ещё не закрыты."""
    return (select(NightCheckItem)
            .join(NightAreaSection, NightAreaSection.id == NightCheckItem.section_id)
            .join(NightReport, NightReport.id == NightAreaSection.report_id)
            .where(NightReport.status == "open", NightAreaSection.status != "done", *where))


def can_edit(db: Session, principal: Principal) -> bool:
    return has_perm(db, principal, "night.edit")


# ─────────────────────────── объекты ───────────────────────────

def list_areas(db: Session) -> list[dict]:
    """Объекты обхода со своими пунктами. effective_total — пунктов в чек-листе объекта:
    шаблон зоны и свои."""
    zones = {z.id: z.name for z in db.scalars(select(NightZone))}
    svc_names = services_map(db)
    out = []
    for area in db.scalars(select(NightArea).order_by(NightArea.sort_order, NightArea.id)):
        items = [{"id": it.id, "text": it.text, "sort_order": it.sort_order, "active": it.active,
                  "service_id": it.service_id, "service_name": svc_names.get(it.service_id or 0, "")}
                 for it in db.scalars(select(ChecklistItem).where(ChecklistItem.area_id == area.id)
                                      .order_by(ChecklistItem.sort_order, ChecklistItem.id))]
        zone_items = len(list(db.scalars(select(ZoneChecklistItem.id).where(
            ZoneChecklistItem.zone_id == area.zone_id, ZoneChecklistItem.active.is_(True))))) if area.zone_id else 0
        own_active = len([i for i in items if i["active"]])
        out.append({"id": area.id, "name": area.name, "category": area.category, "zone_id": area.zone_id,
                    "zone_name": zones.get(area.zone_id, area.category or ""),
                    "sort_order": area.sort_order, "active": area.active,
                    "items": items, "items_total": own_active, "effective_total": zone_items + own_active})
    return out


@transactional
def create_areas_bulk(db: Session, principal: Principal, data: AreaBulkIn) -> int:
    """Создать объекты подряд; объект с уже занятым названием пропускается. Возвращает число созданных."""
    if data.count < 1 or data.count > 200:
        raise Rejected("Количество должно быть от 1 до 200")
    _check_zone(db, data.zone_id)
    created = 0
    for n in range(data.start, data.start + data.count):
        name = f"{data.prefix}{n}".strip()
        if db.scalar(select(NightArea).where(NightArea.name == name)):
            continue
        db.add(NightArea(name=name, category=data.category, zone_id=data.zone_id, sort_order=n % 1000 + 100))
        db.flush()
        created += 1
    audit(db, principal, "night_areas_bulk", f"created:{created}", data.model_dump())
    return created


@transactional
def create_area(db: Session, principal: Principal, data: AreaIn) -> int:
    name = data.name.strip()
    if not name:
        raise Rejected("Введите название области")
    if db.scalar(select(NightArea).where(NightArea.name == name)):
        raise Conflict("Такая область уже есть")
    _check_zone(db, data.zone_id)
    area = NightArea(name=name, category=data.category.strip(), zone_id=data.zone_id,
                     sort_order=data.sort_order, active=data.active)
    db.add(area)
    db.flush()
    audit(db, principal, "night_area_create", f"area:{area.id}", {"name": name})
    return area.id


@transactional
def update_area(db: Session, principal: Principal, area_id: int, data: AreaIn) -> int:
    """Правка объекта. Смена зоны меняет чек-лист: он пересобирается в сменах, где объект ещё
    не начат. Возвращает число пересобранных объектов отчётов."""
    area = _area(db, area_id)
    name = data.name.strip()
    if name and name != area.name and db.scalar(
            select(NightArea).where(NightArea.name == name, NightArea.id != area_id)):
        raise Conflict("Такая область уже есть")
    _check_zone(db, data.zone_id)
    old = {"name": area.name, "category": area.category, "active": area.active, "zone_id": area.zone_id}
    zone_changed = data.zone_id != area.zone_id
    area.name = name or area.name
    area.category = data.category.strip()
    area.zone_id = data.zone_id
    area.sort_order = data.sort_order
    area.active = data.active
    db.flush()
    touched = refresh_free_section(db, area) if zone_changed else 0
    audit(db, principal, "night_area_update", f"area:{area.id}",
          {"old": old, "new": data.model_dump(), "sections_refreshed": touched})
    return touched


@transactional
def delete_area(db: Session, principal: Principal, area_id: int) -> int:
    """Отключить объект: из отчётов открытых смен он убирается вместе с фото пунктов, история
    закрытых смен остаётся. Возвращает число убранных объектов отчётов."""
    area = _area(db, area_id)
    removed = 0
    for rep in db.scalars(select(NightReport).where(NightReport.status == "open")):
        sec = db.scalar(select(NightAreaSection).where(NightAreaSection.report_id == rep.id,
                                                       NightAreaSection.area_id == area_id))
        if sec is not None:
            delete_photo_files(db, "night_item", [i.id for i in sec.items])
            db.delete(sec)
            removed += 1
    area.active = False
    audit(db, principal, "night_area_delete", f"area:{area.id}", {"sections_removed": removed})
    return removed


# ─────────────────────────── свои пункты объекта ───────────────────────────

@transactional
def add_item(db: Session, principal: Principal, area_id: int, data: ItemIn) -> dict:
    """Свой пункт объекта. В открытых сменах добавляется только туда, где объект ещё не начат."""
    area = _area(db, area_id)
    text = data.text.strip()
    if not text:
        raise Rejected("Введите текст пункта")
    _check_service(db, data.service_id)
    item = ChecklistItem(area_id=area.id, text=text[:300], sort_order=data.sort_order,
                         active=data.active, service_id=data.service_id)
    db.add(item)
    db.flush()
    service_name = services_map(db).get(item.service_id or 0, "")
    added = 0
    for sec in db.scalars(select(NightAreaSection)
                          .join(NightReport, NightReport.id == NightAreaSection.report_id)
                          .where(NightReport.status == "open", NightAreaSection.area_id == area_id,
                                 NightAreaSection.status == "free")):
        db.add(NightCheckItem(section_id=sec.id, item_id=item.id, text=item.text, sort_order=item.sort_order,
                              service_id=item.service_id, service_name=service_name))
        sec.snapshot = [*sec.snapshot, {"id": item.id, "src": "area", "text": item.text, "overridden": False,
                                        "service_id": item.service_id, "service_name": service_name}]
        added += 1
    audit(db, principal, "night_item_create", f"item:{item.id}", {"area": area.name, "added_to": added})
    return {"id": item.id, "added_to_open_sections": added}


@transactional
def update_item(db: Session, principal: Principal, item_id: int, data: ItemIn) -> None:
    """Правка своего пункта: текст, порядок и служба уходят в незакрытые объекты открытых смен;
    выключенный пункт без отметки оттуда убирается."""
    item = db.get(ChecklistItem, item_id)
    if item is None:
        raise NotFound("Пункт не найден")
    old_text = item.text
    _check_service(db, data.service_id)
    item.text = data.text.strip()[:300] or item.text
    item.sort_order = data.sort_order
    item.active = data.active
    item.service_id = data.service_id
    service_name = services_map(db).get(item.service_id or 0, "")
    for ni in db.scalars(_open_items(NightCheckItem.item_id == item.id)):
        ni.text = item.text
        ni.sort_order = item.sort_order
        ni.service_id = item.service_id
        ni.service_name = service_name
        if not item.active and not ni.answer:
            ni.section.snapshot = [x for x in ni.section.snapshot if x.get("id") != item.id]
            db.delete(ni)
    audit(db, principal, "night_item_update", f"item:{item.id}", {"text": old_text, **data.model_dump()})


@transactional
def delete_item(db: Session, principal: Principal, item_id: int) -> int:
    """Выключить свой пункт: из незакрытых объектов он исчезает, если не отмечен; в закрытых
    остаётся. Возвращает число убранных пунктов отчётов."""
    item = db.get(ChecklistItem, item_id)
    if item is None:
        raise NotFound("Пункт не найден")
    item.active = False
    removed = 0
    for ni in db.scalars(_open_items(NightCheckItem.item_id == item.id, NightCheckItem.answer == "")):
        db.delete(ni)
        removed += 1
    audit(db, principal, "night_item_delete", f"item:{item_id}", {"removed_from_open": removed})
    return removed


# ─────────────────────────── зоны ───────────────────────────

def list_zones(db: Session) -> list[dict]:
    """Зоны обхода: сколько в зоне действующих объектов и пунктов шаблона."""
    areas_cnt = dict(db.execute(
        select(NightArea.zone_id, func.count(NightArea.id))
        .where(NightArea.active.is_(True), NightArea.zone_id.is_not(None)).group_by(NightArea.zone_id)).all())
    items_cnt = dict(db.execute(
        select(ZoneChecklistItem.zone_id, func.count(ZoneChecklistItem.id))
        .where(ZoneChecklistItem.active.is_(True)).group_by(ZoneChecklistItem.zone_id)).all())
    return [zone_dict(z, areas_total=areas_cnt.get(z.id, 0), items_total=items_cnt.get(z.id, 0))
            for z in db.scalars(select(NightZone).order_by(NightZone.sort_order, NightZone.id))]


@transactional
def create_zone(db: Session, principal: Principal, data: ZoneIn) -> dict:
    name = data.name.strip()
    if not name:
        raise Rejected("Введите название зоны")
    if db.scalar(select(NightZone).where(NightZone.name == name)):
        raise Conflict("Такая зона уже есть")
    zone = NightZone(name=name[:160], sort_order=data.sort_order, active=data.active)
    db.add(zone)
    db.flush()
    audit(db, principal, "night_zone_create", f"zone:{zone.id}", data.model_dump())
    return zone_dict(zone)


@transactional
def update_zone(db: Session, principal: Principal, zone_id: int, data: ZoneIn) -> dict:
    """Правка зоны. Новое название уходит в отчёты открытых смен, закрытые хранят прежнее."""
    zone = _zone(db, zone_id)
    name = data.name.strip()
    if not name:
        raise Rejected("Введите название зоны")
    if db.scalar(select(NightZone).where(NightZone.name == name, NightZone.id != zone_id)) is not None:
        raise Conflict("Такая зона уже есть")
    old = {"name": zone.name, "sort_order": zone.sort_order, "active": zone.active}
    zone.name = name[:160]
    zone.sort_order = data.sort_order
    zone.active = data.active
    for sec in db.scalars(select(NightAreaSection)
                          .join(NightReport, NightReport.id == NightAreaSection.report_id)
                          .where(NightAreaSection.zone_id == zone.id, NightReport.status == "open")):
        sec.zone_name = zone.name
    audit(db, principal, "night_zone_update", f"zone:{zone.id}", {"old": old, "new": data.model_dump()})
    return zone_dict(zone)


@transactional
def delete_zone(db: Session, principal: Principal, zone_id: int) -> int:
    """Отключить зону: она перестаёт предлагаться в справочниках, её объекты и история смен
    остаются. Возвращает число действующих объектов зоны."""
    zone = _zone(db, zone_id)
    zone.active = False
    areas = len(list(db.scalars(select(NightArea.id).where(NightArea.zone_id == zone.id,
                                                           NightArea.active.is_(True)))))
    audit(db, principal, "night_zone_delete", f"zone:{zone_id}", {"areas_left": areas})
    return areas


# ─────────────────────────── шаблон чек-листа зоны ───────────────────────────

def zone_items(db: Session, zone_id: int) -> dict:
    """Шаблон чек-листа зоны и её объекты. overrides — у скольких объектов пункт изменён."""
    zone = _zone(db, zone_id)
    areas = [{"id": a.id, "name": a.name, "active": bool(a.active)}
             for a in db.scalars(select(NightArea).where(NightArea.zone_id == zone_id)
                                 .order_by(NightArea.sort_order, NightArea.id))]
    area_ids = [a["id"] for a in areas]
    overrides = dict(db.execute(select(ChecklistOverride.zone_item_id, func.count(ChecklistOverride.id))
                                .where(ChecklistOverride.area_id.in_(area_ids))
                                .group_by(ChecklistOverride.zone_item_id)).all()) if area_ids else {}
    svc_names = services_map(db)
    items = [{"id": i.id, "text": i.text, "sort_order": i.sort_order, "active": bool(i.active),
              "overrides": overrides.get(i.id, 0), "service_id": i.service_id,
              "service_name": svc_names.get(i.service_id or 0, "")}
             for i in db.scalars(select(ZoneChecklistItem).where(ZoneChecklistItem.zone_id == zone_id)
                                 .order_by(ZoneChecklistItem.sort_order, ZoneChecklistItem.id))]
    return {"zone": zone_dict(zone, areas_total=len(areas), items_total=len([i for i in items if i["active"]])),
            "items": items, "areas": areas}


@transactional
def add_zone_item(db: Session, principal: Principal, zone_id: int, data: ItemIn) -> dict:
    """Пункт шаблона зоны: попадает в чек-листы всех её объектов. В открытых сменах — только
    туда, где объект ещё не начат."""
    zone = _zone(db, zone_id)
    text = data.text.strip()
    if not text:
        raise Rejected("Введите текст пункта")
    _check_service(db, data.service_id)
    item = ZoneChecklistItem(zone_id=zone.id, text=text[:300], sort_order=data.sort_order,
                             active=data.active, service_id=data.service_id)
    db.add(item)
    db.flush()
    refreshed = sum(refresh_free_section(db, area) for area in db.scalars(
        select(NightArea).where(NightArea.zone_id == zone.id, NightArea.active.is_(True))))
    audit(db, principal, "night_zone_item_create", f"zone:{zone.id}",
          {**data.model_dump(), "sections_refreshed": refreshed})
    return {"id": item.id, "sections_refreshed": refreshed}


def _remove_zone_item_from_open(db: Session, item: ZoneChecklistItem) -> int:
    """Убрать пункт шаблона из незакрытых объектов открытых смен; отмеченные остаются."""
    removed = 0
    for ni in db.scalars(_open_items(NightCheckItem.zone_item_id == item.id, NightCheckItem.answer == "")):
        ni.section.snapshot = [x for x in ni.section.snapshot
                               if not (x.get("src") == "zone" and x.get("id") == item.id)]
        db.delete(ni)
        removed += 1
    return removed


@transactional
def update_zone_item(db: Session, principal: Principal, item_id: int, data: ItemIn) -> int:
    """Правка пункта шаблона: текст и служба уходят в незакрытые объекты открытых смен, кроме
    объектов со своей формулировкой или своей службой. Возвращает число убранных пунктов
    отчётов (если пункт выключен)."""
    item = db.get(ZoneChecklistItem, item_id)
    if item is None:
        raise NotFound("Пункт не найден")
    _check_service(db, data.service_id)
    old_text = item.text
    item.text = data.text.strip()[:300] or item.text
    item.sort_order = data.sort_order
    item.active = data.active
    item.service_id = data.service_id
    service_name = services_map(db).get(item.service_id or 0, "")
    overrides = {o.area_id: o for o in db.scalars(select(ChecklistOverride).where(
        ChecklistOverride.zone_item_id == item.id))}
    for ni in db.scalars(_open_items(NightCheckItem.zone_item_id == item.id)):
        ov = overrides.get(ni.section.area_id)
        if ov is None or not ov.text:
            ni.text = item.text
        ni.sort_order = item.sort_order
        if ov is None or not ov.service_id:
            ni.service_id = item.service_id
            ni.service_name = service_name
    removed = _remove_zone_item_from_open(db, item) if not item.active else 0
    audit(db, principal, "night_zone_item_update", f"zone_item:{item.id}",
          {"old_text": old_text, **data.model_dump(), "removed_from_open": removed})
    return removed


@transactional
def delete_zone_item(db: Session, principal: Principal, item_id: int) -> int:
    """Выключить пункт шаблона: из незакрытых объектов открытых смен он исчезает, если не
    отмечен. Возвращает число убранных пунктов отчётов."""
    item = db.get(ZoneChecklistItem, item_id)
    if item is None:
        raise NotFound("Пункт не найден")
    item.active = False
    removed = _remove_zone_item_from_open(db, item)
    audit(db, principal, "night_zone_item_delete", f"zone_item:{item_id}", {"removed_from_open": removed})
    return removed


# ─────────────────────────── чек-лист объекта и его особенности ───────────────────────────

def area_checklist(db: Session, area_id: int) -> dict:
    """Чек-лист объекта для настроек: шаблон зоны с особенностями объекта, свои пункты и итог."""
    area = _area(db, area_id)
    zone = db.get(NightZone, area.zone_id) if area.zone_id else None
    overrides = {o.zone_item_id: o for o in db.scalars(select(ChecklistOverride)
                                                       .where(ChecklistOverride.area_id == area.id))}
    svc_names = services_map(db)
    template = []
    if zone is not None:
        for i in db.scalars(select(ZoneChecklistItem)
                            .where(ZoneChecklistItem.zone_id == zone.id, ZoneChecklistItem.active.is_(True))
                            .order_by(ZoneChecklistItem.sort_order, ZoneChecklistItem.id)):
            ov = overrides.get(i.id)
            sid = ov.service_id if (ov and ov.service_id) else i.service_id
            template.append({
                "id": i.id, "text": i.text, "sort_order": i.sort_order,
                "override_text": ov.text if ov else "", "disabled": bool(ov.disabled) if ov else False,
                "effective_text": (ov.text if ov and ov.text else i.text),
                "in_checklist": not (ov.disabled if ov else False),
                "service_id": i.service_id, "service_name": svc_names.get(i.service_id or 0, ""),
                "override_service_id": ov.service_id if ov else None,
                "override_service_name": svc_names.get(ov.service_id or 0, "") if ov else "",
                "effective_service_id": sid, "effective_service_name": svc_names.get(sid or 0, "")})
    own = [{"id": i.id, "text": i.text, "sort_order": i.sort_order, "active": bool(i.active),
            "service_id": i.service_id, "service_name": svc_names.get(i.service_id or 0, "")}
           for i in db.scalars(select(ChecklistItem)
                               .where(ChecklistItem.area_id == area.id, ChecklistItem.active.is_(True))
                               .order_by(ChecklistItem.sort_order, ChecklistItem.id))]
    return {"area": {"id": area.id, "name": area.name, "zone_id": area.zone_id,
                     "zone_name": zone.name if zone else (area.category or ""), "active": bool(area.active)},
            "zone_items": template, "own_items": own, "effective": effective_items(db, area)}


@transactional
def set_override(db: Session, principal: Principal, area_id: int, zone_item_id: int, data: OverrideIn) -> dict:
    """Особенность объекта для пункта шаблона зоны. Пустая формулировка, пункт не отключён и
    служба не задана — «как в шаблоне»: запись особенности удаляется. Применяется к сменам,
    где объект ещё не начат."""
    area = _area(db, area_id)
    item = db.get(ZoneChecklistItem, zone_item_id)
    if item is None:
        raise NotFound("Пункт шаблона зоны не найден")
    if item.zone_id != area.zone_id:
        raise Rejected("Пункт не из шаблона зоны этого объекта")
    _check_service(db, data.service_id)
    text = data.text.strip()[:300]
    ov = db.scalar(select(ChecklistOverride).where(ChecklistOverride.area_id == area.id,
                                                  ChecklistOverride.zone_item_id == item.id))
    if not text and not data.disabled and not data.service_id:
        if ov is not None:
            db.delete(ov)
    elif ov is None:
        db.add(ChecklistOverride(area_id=area.id, zone_item_id=item.id, text=text,
                                 disabled=bool(data.disabled), service_id=data.service_id))
    else:
        ov.text = text
        ov.disabled = bool(data.disabled)
        ov.service_id = data.service_id
    db.flush()
    touched = refresh_free_section(db, area)
    audit(db, principal, "night_override_set", f"area:{area.id}",
          {"zone_item_id": item.id, "text": text, "disabled": bool(data.disabled),
           "service_id": data.service_id, "sections_refreshed": touched})
    return {"sections_refreshed": touched, "effective": effective_items(db, area)}


@transactional
def reset_override(db: Session, principal: Principal, area_id: int, zone_item_id: int) -> int:
    """Убрать особенность: пункт у объекта снова как в шаблоне зоны. Возвращает число
    пересобранных объектов отчётов."""
    area = _area(db, area_id)
    ov = db.scalar(select(ChecklistOverride).where(ChecklistOverride.area_id == area.id,
                                                  ChecklistOverride.zone_item_id == zone_item_id))
    touched = 0
    if ov is not None:
        db.delete(ov)
        db.flush()              # чек-лист пересобирается уже без особенности
        touched = refresh_free_section(db, area)
    audit(db, principal, "night_override_reset", f"area:{area.id}",
          {"zone_item_id": zone_item_id, "sections_refreshed": touched})
    return touched


# ─────────────────────────── ответственные службы ───────────────────────────

def list_services(db: Session) -> list[dict]:
    """Службы: каналы, получатели и сколько действующих пунктов за каждой закреплено."""
    zone_counts = dict(db.execute(
        select(ZoneChecklistItem.service_id, func.count(ZoneChecklistItem.id))
        .where(ZoneChecklistItem.active.is_(True), ZoneChecklistItem.service_id.is_not(None))
        .group_by(ZoneChecklistItem.service_id)).all())
    own_counts = dict(db.execute(
        select(ChecklistItem.service_id, func.count(ChecklistItem.id))
        .where(ChecklistItem.active.is_(True), ChecklistItem.service_id.is_not(None))
        .group_by(ChecklistItem.service_id)).all())
    return [service_dict(s, items_total=zone_counts.get(s.id, 0) + own_counts.get(s.id, 0))
            for s in db.scalars(select(ResponsibilityService)
                                .order_by(ResponsibilityService.sort_order, ResponsibilityService.id))]


def _service_name_taken(db: Session, name: str, exclude_id: Optional[int] = None) -> bool:
    """Занято ли название службы — без учёта регистра."""
    want = name.strip().casefold()
    query = select(ResponsibilityService.id, ResponsibilityService.name)
    if exclude_id is not None:
        query = query.where(ResponsibilityService.id != exclude_id)
    return any(n.strip().casefold() == want for _, n in db.execute(query).all())


def _service_fields(db: Session, data: ServiceIn, exclude_id: Optional[int] = None) -> dict:
    """Проверенные поля службы: название свободно, выбран канал, у письма есть ящик."""
    name = data.name.strip()[:160]
    if not name:
        raise Rejected("Введите название службы")
    if _service_name_taken(db, name, exclude_id):
        raise Conflict("Служба с таким названием уже есть")
    if not data.use_telegram and not data.use_email:
        raise Rejected("Выберите хотя бы один канал: чат Telegram и/или письмо")
    if data.use_email and "@" not in (data.email_to or ""):
        raise Rejected("Укажите почтовый ящик службы (канал «письмо» включён)")
    return {"name": name, "sort_order": data.sort_order, "active": data.active,
            "use_telegram": data.use_telegram, "use_email": data.use_email,
            "email_to": data.email_to.strip()[:200], "email_copy": data.email_copy.strip()[:400],
            "chat_ids": list(data.chat_ids), "note": data.note.strip()[:300]}


@transactional
def create_service(db: Session, principal: Principal, data: ServiceIn) -> dict:
    svc = ResponsibilityService(**_service_fields(db, data))
    db.add(svc)
    db.flush()
    audit(db, principal, "night_service_create", f"service:{svc.id}", data.model_dump())
    return service_dict(svc)


@transactional
def update_service(db: Session, principal: Principal, service_id: int, data: ServiceIn) -> dict:
    """Правка службы. Новое название уходит в незакрытые объекты открытых смен, закрытые
    хранят прежнее."""
    svc = db.get(ResponsibilityService, service_id)
    if svc is None:
        raise NotFound("Служба не найдена")
    fields = _service_fields(db, data, exclude_id=svc.id)
    old = service_dict(svc)
    for key, value in fields.items():
        setattr(svc, key, value)
    db.flush()
    updated = 0
    for ni in db.scalars(_open_items(NightCheckItem.service_id == svc.id)):
        ni.service_name = svc.name
        updated += 1
    audit(db, principal, "night_service_update", f"service:{svc.id}",
          {"old": old, "new": service_dict(svc), "open_items_updated": updated})
    return {"service": service_dict(svc), "open_items_updated": updated}


@transactional
def delete_service(db: Session, principal: Principal, service_id: int) -> int:
    """Отключить службу: она не предлагается в справочнике и не участвует в новых отправках;
    пункты и история закрытых смен остаются. Возвращает число пунктов шаблонов зон, которые
    за ней закреплены, — их стоит переназначить."""
    svc = db.get(ResponsibilityService, service_id)
    if svc is None:
        raise NotFound("Служба не найдена")
    svc.active = False
    items_total = db.scalar(select(func.count(ZoneChecklistItem.id)).where(
        ZoneChecklistItem.service_id == svc.id, ZoneChecklistItem.active.is_(True))) or 0
    audit(db, principal, "night_service_delete", f"service:{service_id}",
          {"name": svc.name, "items_total": items_total})
    return items_total
