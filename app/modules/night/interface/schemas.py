"""Модели ответов API ночного обхода: справочники."""
from __future__ import annotations

from typing import Literal, Optional

from app.core.schemas import ApiModel

# ── объекты и свои пункты ────────────────────────────────────────────────────


class OwnItemOut(ApiModel):
    """Свой пункт объекта."""

    id: int
    text: str
    sort_order: int
    active: bool
    service_id: Optional[int]
    service_name: str


class AreaOut(ApiModel):
    id: int
    name: str
    category: str
    zone_id: Optional[int]
    zone_name: str
    sort_order: int
    active: bool
    items: list[OwnItemOut]
    items_total: int            # действующих своих пунктов
    effective_total: int        # пунктов в чек-листе объекта: шаблон зоны и свои


class AreasOut(ApiModel):
    areas: list[AreaOut]
    can_edit: bool


class AreasCreatedOut(ApiModel):
    created: int


class CreatedOut(ApiModel):
    id: int


class SectionsRefreshedOut(ApiModel):
    ok: bool = True
    sections_refreshed: int     # объектов в открытых сменах, чей чек-лист пересобран


class SectionsRemovedOut(ApiModel):
    ok: bool = True
    sections_removed: int


class ItemAddedOut(ApiModel):
    id: int
    added_to_open_sections: int


class RemovedFromOpenOut(ApiModel):
    ok: bool = True
    removed_from_open: int      # пунктов, убранных из незакрытых объектов открытых смен


# ── зоны и шаблон чек-листа ──────────────────────────────────────────────────


class ZoneOut(ApiModel):
    id: int
    name: str
    sort_order: int
    active: bool
    areas_total: int
    items_total: int
    created_at: Optional[str]


class ZonesOut(ApiModel):
    zones: list[ZoneOut]
    can_edit: bool


class ZoneUpdatedOut(ApiModel):
    ok: bool = True
    zone: ZoneOut


class ZoneDeletedOut(ApiModel):
    ok: bool = True
    areas_left: int             # действующих объектов осталось в отключённой зоне


class ZoneItemOut(ApiModel):
    id: int
    text: str
    sort_order: int
    active: bool
    overrides: int              # у скольких объектов пункт изменён
    service_id: Optional[int]
    service_name: str


class ZoneAreaOut(ApiModel):
    id: int
    name: str
    active: bool


class ZoneItemsOut(ApiModel):
    zone: ZoneOut
    items: list[ZoneItemOut]
    areas: list[ZoneAreaOut]


class ZoneItemAddedOut(ApiModel):
    ok: bool = True
    id: int
    sections_refreshed: int


# ── чек-лист объекта и его особенности ───────────────────────────────────────


class ChecklistAreaOut(ApiModel):
    id: int
    name: str
    zone_id: Optional[int]
    zone_name: str
    active: bool


class TemplateItemOut(ApiModel):
    """Пункт шаблона зоны, как он действует у объекта."""

    id: int
    text: str
    sort_order: int
    override_text: str
    disabled: bool
    effective_text: str
    in_checklist: bool
    service_id: Optional[int]
    service_name: str
    override_service_id: Optional[int]
    override_service_name: str
    effective_service_id: Optional[int]
    effective_service_name: str


class EffectiveItemOut(ApiModel):
    """Пункт итогового чек-листа объекта; id — пункта шаблона зоны или своего, по src."""

    id: int
    src: Literal["zone", "area"]
    text: str
    overridden: bool
    service_id: Optional[int]
    service_name: str
    service_own: bool           # у объекта своя служба, а не как в шаблоне зоны


class AreaChecklistOut(ApiModel):
    area: ChecklistAreaOut
    zone_items: list[TemplateItemOut]
    own_items: list[OwnItemOut]
    effective: list[EffectiveItemOut]


class OverrideSetOut(ApiModel):
    ok: bool = True
    sections_refreshed: int
    effective: list[EffectiveItemOut]


# ── ответственные службы ─────────────────────────────────────────────────────


class ServiceOut(ApiModel):
    id: int
    name: str
    sort_order: int
    active: bool
    use_telegram: bool
    use_email: bool
    email_to: str
    email_copy: str
    chat_ids: list[int]
    note: str
    items_total: int
    ready_telegram: bool        # канал включён и получатель заполнен
    ready_email: bool
    ready: bool
    created_at: Optional[str]


class ServicesOut(ApiModel):
    services: list[ServiceOut]
    can_edit: bool


class ServiceCreatedOut(ApiModel):
    ok: bool = True
    id: int
    service: ServiceOut


class ServiceUpdatedOut(ApiModel):
    ok: bool = True
    service: ServiceOut
    open_items_updated: int     # пунктов открытых смен, где обновлено название службы


class ServiceDeletedOut(ApiModel):
    ok: bool = True
    items_total: int            # пунктов шаблонов зон, закреплённых за отключённой службой
