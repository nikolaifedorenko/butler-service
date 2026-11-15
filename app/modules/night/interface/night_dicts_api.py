"""Справочники ночного обхода: объекты и их пункты, зоны и шаблоны чек-листов, особенности
объектов, ответственные службы. Смотреть — night.view, править — night.edit.
Правила — в ``application/dictionaries.py``."""
from __future__ import annotations

from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.auth import Principal
from app.core.db import get_db
from app.core.permissions import require_perm
from app.core.schemas import Ok

from ..application import dictionaries as dicts
from ..application.dictionaries import AreaBulkIn, AreaIn, ItemIn, OverrideIn, ServiceIn, ZoneIn
from .night_common import router
from .schemas import (
    AreaChecklistOut,
    AreasCreatedOut,
    AreasOut,
    CreatedOut,
    ItemAddedOut,
    OverrideSetOut,
    RemovedFromOpenOut,
    SectionsRefreshedOut,
    SectionsRemovedOut,
    ServiceCreatedOut,
    ServiceDeletedOut,
    ServicesOut,
    ServiceUpdatedOut,
    ZoneDeletedOut,
    ZoneItemAddedOut,
    ZoneItemsOut,
    ZoneOut,
    ZonesOut,
    ZoneUpdatedOut,
)

VIEW = require_perm("night.view")
EDIT = require_perm("night.edit")

# ─────────────────────────── объекты и свои пункты ───────────────────────────


@router.get("/areas", response_model=AreasOut)
def list_areas(principal: Principal = Depends(VIEW), db: Session = Depends(get_db)):
    """Объекты обхода с их пунктами."""
    return {"areas": dicts.list_areas(db), "can_edit": dicts.can_edit(db, principal)}


@router.post("/areas/bulk", response_model=AreasCreatedOut)
def create_areas_bulk(payload: AreaBulkIn, principal: Principal = Depends(EDIT), db: Session = Depends(get_db)):
    """Создать однотипные объекты подряд («Вилла », 4001, 12 штук)."""
    return {"created": dicts.create_areas_bulk(db, principal, payload)}


@router.post("/areas", response_model=CreatedOut)
def create_area(payload: AreaIn, principal: Principal = Depends(EDIT), db: Session = Depends(get_db)):
    return {"id": dicts.create_area(db, principal, payload)}


@router.put("/areas/{area_id}", response_model=SectionsRefreshedOut)
def update_area(area_id: int, payload: AreaIn, principal: Principal = Depends(EDIT),
                db: Session = Depends(get_db)):
    return {"sections_refreshed": dicts.update_area(db, principal, area_id, payload)}


@router.delete("/areas/{area_id}", response_model=SectionsRemovedOut)
def delete_area(area_id: int, principal: Principal = Depends(EDIT), db: Session = Depends(get_db)):
    """Отключить объект: история закрытых смен остаётся."""
    return {"sections_removed": dicts.delete_area(db, principal, area_id)}


@router.post("/areas/{area_id}/items", response_model=ItemAddedOut)
def add_item(area_id: int, payload: ItemIn, principal: Principal = Depends(EDIT), db: Session = Depends(get_db)):
    return dicts.add_item(db, principal, area_id, payload)


@router.put("/items/{item_id}", response_model=Ok)
def update_item(item_id: int, payload: ItemIn, principal: Principal = Depends(EDIT), db: Session = Depends(get_db)):
    dicts.update_item(db, principal, item_id, payload)
    return Ok()


@router.delete("/items/{item_id}", response_model=RemovedFromOpenOut)
def delete_item(item_id: int, principal: Principal = Depends(EDIT), db: Session = Depends(get_db)):
    """Выключить пункт: в закрытых объектах он остаётся."""
    return {"removed_from_open": dicts.delete_item(db, principal, item_id)}


# ─────────────────────────── зоны и шаблон чек-листа ───────────────────────────


@router.get("/zones", response_model=ZonesOut)
def list_zones(principal: Principal = Depends(VIEW), db: Session = Depends(get_db)):
    """Зоны обхода: сколько в зоне объектов и пунктов шаблона."""
    return {"zones": dicts.list_zones(db), "can_edit": dicts.can_edit(db, principal)}


@router.post("/zones", response_model=ZoneOut)
def create_zone(payload: ZoneIn, principal: Principal = Depends(EDIT), db: Session = Depends(get_db)):
    return dicts.create_zone(db, principal, payload)


@router.put("/zones/{zone_id}", response_model=ZoneUpdatedOut)
def update_zone(zone_id: int, payload: ZoneIn, principal: Principal = Depends(EDIT), db: Session = Depends(get_db)):
    return {"zone": dicts.update_zone(db, principal, zone_id, payload)}


@router.delete("/zones/{zone_id}", response_model=ZoneDeletedOut)
def delete_zone(zone_id: int, principal: Principal = Depends(EDIT), db: Session = Depends(get_db)):
    """Отключить зону: объекты и история смен сохраняются."""
    return {"areas_left": dicts.delete_zone(db, principal, zone_id)}


@router.get("/zones/{zone_id}/items", response_model=ZoneItemsOut)
def zone_items(zone_id: int, principal: Principal = Depends(VIEW), db: Session = Depends(get_db)):
    """Шаблон чек-листа зоны и её объекты."""
    return dicts.zone_items(db, zone_id)


@router.post("/zones/{zone_id}/items", response_model=ZoneItemAddedOut)
def add_zone_item(zone_id: int, payload: ItemIn, principal: Principal = Depends(EDIT),
                  db: Session = Depends(get_db)):
    """Пункт шаблона зоны: попадает в чек-листы всех её объектов."""
    return dicts.add_zone_item(db, principal, zone_id, payload)


@router.put("/zone-items/{item_id}", response_model=RemovedFromOpenOut)
def update_zone_item(item_id: int, payload: ItemIn, principal: Principal = Depends(EDIT),
                     db: Session = Depends(get_db)):
    return {"removed_from_open": dicts.update_zone_item(db, principal, item_id, payload)}


@router.delete("/zone-items/{item_id}", response_model=RemovedFromOpenOut)
def delete_zone_item(item_id: int, principal: Principal = Depends(EDIT), db: Session = Depends(get_db)):
    """Выключить пункт шаблона: в закрытых объектах он остаётся."""
    return {"removed_from_open": dicts.delete_zone_item(db, principal, item_id)}


# ─────────────────────────── чек-лист объекта и его особенности ───────────────────────────


@router.get("/areas/{area_id}/checklist", response_model=AreaChecklistOut)
def area_checklist(area_id: int, principal: Principal = Depends(VIEW), db: Session = Depends(get_db)):
    """Чек-лист объекта: шаблон зоны с особенностями, свои пункты и итог."""
    return dicts.area_checklist(db, area_id)


@router.put("/areas/{area_id}/overrides/{zone_item_id}", response_model=OverrideSetOut)
def set_override(area_id: int, zone_item_id: int, payload: OverrideIn,
                 principal: Principal = Depends(EDIT), db: Session = Depends(get_db)):
    """Особенность объекта для пункта шаблона: своя формулировка, своя служба или отключение."""
    return dicts.set_override(db, principal, area_id, zone_item_id, payload)


@router.delete("/areas/{area_id}/overrides/{zone_item_id}", response_model=SectionsRefreshedOut)
def reset_override(area_id: int, zone_item_id: int, principal: Principal = Depends(EDIT),
                   db: Session = Depends(get_db)):
    """Убрать особенность: пункт у объекта снова как в шаблоне зоны."""
    return {"sections_refreshed": dicts.reset_override(db, principal, area_id, zone_item_id)}


# ─────────────────────────── ответственные службы ───────────────────────────


@router.get("/services", response_model=ServicesOut)
def list_services(principal: Principal = Depends(VIEW), db: Session = Depends(get_db)):
    """Службы: каналы, получатели и сколько пунктов за каждой закреплено."""
    return {"services": dicts.list_services(db), "can_edit": dicts.can_edit(db, principal)}


@router.post("/services", response_model=ServiceCreatedOut)
def create_service(payload: ServiceIn, principal: Principal = Depends(EDIT), db: Session = Depends(get_db)):
    service = dicts.create_service(db, principal, payload)
    return {"id": service["id"], "service": service}


@router.put("/services/{service_id}", response_model=ServiceUpdatedOut)
def update_service(service_id: int, payload: ServiceIn, principal: Principal = Depends(EDIT),
                   db: Session = Depends(get_db)):
    return dicts.update_service(db, principal, service_id, payload)


@router.delete("/services/{service_id}", response_model=ServiceDeletedOut)
def delete_service(service_id: int, principal: Principal = Depends(EDIT), db: Session = Depends(get_db)):
    """Отключить службу: пункты и история закрытых смен остаются."""
    return {"items_total": dicts.delete_service(db, principal, service_id)}
