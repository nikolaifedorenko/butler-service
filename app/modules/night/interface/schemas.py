"""Модели ответов API ночного обхода: справочники, ход смены, замечания и отправка."""
from __future__ import annotations

from typing import Literal, Optional

from app.core.schemas import ApiModel, PhotoOut
from app.modules.cars.application.schemas import NightCarCheckSavedOut
from app.modules.notify.application.schemas import DispatchOut

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


# ═════════════════════════════ ход смены ═════════════════════════════


class CheckItemOut(ApiModel):
    """Пункт чек-листа объекта в отчёте смены."""

    id: int
    item_id: Optional[int]          # свой пункт объекта; у пункта шаблона зоны — пусто
    text: str
    sort_order: int
    service_id: Optional[int]
    service_name: str               # название службы, каким оно было в смену
    answer: Literal["", "ok", "bad"]
    answer_title: str
    comment: str
    answered_by_name: str
    answered_at: Optional[str]


class CheckItemPhotosOut(CheckItemOut):
    photos: list[PhotoOut]


class SectionBriefOut(ApiModel):
    """Объект обхода в отчёте смены; шаг «Проверка электрокаров» — объект с is_cars."""

    id: int
    area_id: Optional[int]
    name: str
    category: str
    zone_id: Optional[int]
    zone_name: str
    is_cars: bool
    status: Literal["free", "taken", "done"]
    status_title: str
    taken_by: Optional[int]
    taken_by_name: str
    taken_at: Optional[str]
    closed_at: Optional[str]
    items_total: int
    items_answered: int
    items_bad: int
    items_unanswered: int


class SectionOut(SectionBriefOut):
    items: list[CheckItemOut]


class SectionPhotosOut(SectionBriefOut):
    items: list[CheckItemPhotosOut]


class ProgressOut(ApiModel):
    total: int
    done: int
    taken: int
    free: int


class ZoneProgressOut(ApiModel):
    zone_id: Optional[int]          # пусто — объекты без зоны
    name: str
    areas_total: int
    done: int
    taken: int
    free: int
    items_total: int
    items_answered: int
    items_bad: int
    items_unanswered: int


class ReportBase(ApiModel):
    id: int
    date: str                       # дата начала смены
    shift_label: str
    status: Literal["open", "closed"]
    result: str                     # full | partial | '' — пока смена открыта
    result_title: str
    closed_at: Optional[str]
    close_reason: str               # auto | manual | ''
    reopened_at: Optional[str]      # переоткрыта вручную: автозакрытие выключено
    deadline: str                   # момент автозакрытия
    readonly: bool
    cars_step_done: bool
    progress: ProgressOut
    zones: list[ZoneProgressOut]


class ReportBriefOut(ReportBase):
    """Отчёт в архиве: без пунктов объектов."""

    areas: list[SectionBriefOut]


class CarCheckOut(ApiModel):
    """Отметка кара в обходе смены."""

    id: int
    car_id: Optional[int]
    car_number: str
    checker_name: str
    checked_at: Optional[str]
    found: bool
    location: str
    found_location: str
    moved: bool
    canopy: bool
    charge: str
    on_charge: bool
    condition: str
    trash: bool
    clean: bool
    comment: str
    taken_after_check: bool
    photos: list[PhotoOut]


class InterceptionOut(ApiModel):
    """Перехват объекта: один батлер взял объект, который вёл другой."""

    id: int
    ts: Optional[str]
    area_name: str
    from_user_name: str
    to_user_name: str


class ReportOut(ReportBase):
    """Отчёт смены целиком."""

    areas: list[SectionPhotosOut]
    car_checks: list[CarCheckOut]
    interceptions: list[InterceptionOut]


class ReportsOut(ApiModel):
    reports: list[ReportBriefOut]


class ReportEnvelopeOut(ApiModel):
    report: ReportOut


class ReportChangedOut(ApiModel):
    ok: bool = True
    report: ReportOut


class TodayReportOut(ApiModel):
    available: Literal[True]
    report: ReportOut


class TodayPendingOut(ApiModel):
    """Отчёта текущей смены ещё нет."""

    available: Literal[False]
    shift_date: str
    note: str


class SectionTakenOut(ApiModel):
    ok: bool = True
    section: SectionOut
    warning: Optional[str]          # перехват или переоткрытие объекта
    already: bool                   # объект и так был за пользователем


class SectionChangedOut(ApiModel):
    ok: bool = True
    section: SectionOut


class AnswerOut(ApiModel):
    id: int
    answer: str
    comment: str


class ItemAnsweredOut(ApiModel):
    ok: bool = True
    item: AnswerOut


class PhotoAddedOut(ApiModel):
    id: int
    url: str
    media_type: str


class ItemPhotoOut(ApiModel):
    ok: bool = True
    photo: PhotoAddedOut


class CarCheckedOut(ApiModel):
    ok: bool = True
    check: NightCarCheckSavedOut


class CarsFinishedOut(ApiModel):
    ok: bool = True
    cars_step_done: bool


# ═════════════════════════════ замечания и отправка ═════════════════════════════


class DefectOut(ApiModel):
    """Позиция к отправке службе: «не ОК», «не проверено» или исправленное после отправки."""

    id: int
    kind: Literal["bad", "unchecked", "fixed"]
    kind_title: str
    section_id: int
    area_id: Optional[int]
    area: str
    zone: str
    text: str
    comment: str
    service_id: Optional[int]
    service_name: str
    answered_by_name: str
    answered_at: Optional[str]
    media: list[PhotoOut]
    dispatched: bool
    dispatched_at: Optional[str]
    dispatch_id: Optional[int]
    fixed_after_dispatch: bool
    sendable: bool                  # ещё не отправлялась и не исправлена после отправки


class DefectCountsOut(ApiModel):
    total: int
    bad: int
    unchecked: int
    fixed_after_dispatch: int
    sendable: int
    dispatched: int
    without_service: int


class GroupCountsOut(ApiModel):
    total: int
    sendable: int
    bad: int
    unchecked: int
    dispatched: int
    fixed_after_dispatch: int


class DefectGroupOut(ApiModel):
    """Позиции одной службы и готовность отправить их ей."""

    service_id: Optional[int]       # пусто — позиции без службы
    service_name: str
    sort_order: int
    active: bool
    use_telegram: bool
    use_email: bool
    chat_ids: list[int]
    email_to: list[str]
    email_copy: list[str]
    note: str
    problems: list[str]             # почему отправить нельзя
    defects: list[DefectOut]
    sendable_count: int
    counts: GroupCountsOut
    ready: bool
    channels: list[str]


class ReportShortOut(ApiModel):
    id: int
    date: str
    shift_label: str
    status: str
    readonly: bool


class TemplateOut(ApiModel):
    text: str
    placeholders: list[str]


class TransportOut(ApiModel):
    telegram: bool
    email: bool


class DefectsOut(ApiModel):
    """Экран «Недостатки смены»."""

    report: ReportShortOut
    duty: str                       # кто вёл обход
    counts: DefectCountsOut
    items: list[DefectOut]
    groups: list[DefectGroupOut]
    dispatches: list[DispatchOut]
    template: TemplateOut
    transport: TransportOut         # какие каналы доставки настроены


class SkippedGroupOut(ApiModel):
    service_id: Optional[int]
    service_name: str
    defects: int
    problems: list[str]


class DispatchResultOut(ApiModel):
    ok: bool = True
    sent: int
    failed: int
    queued: int                     # доставки, которые ещё идут
    marked: int                     # позиций помечено отправленными
    dispatches: list[DispatchOut]
    skipped: list[SkippedGroupOut]  # службы, которым отправить нельзя, с причинами


class DispatchesOut(ApiModel):
    dispatches: list[DispatchOut]


class PreviewMessageOut(ApiModel):
    service_id: Optional[int]
    service_name: str
    channels: list[str]
    problems: list[str]
    defects: int
    message: str


class PreviewOut(ApiModel):
    ok: bool = True
    messages: list[PreviewMessageOut]
    domain: str
