"""Модели ответов модуля «Шахматка».

Каждый ключ ответа присутствует всегда; значение, которого в данном случае нет, — ``None``.
Модели запросов лежат рядом с операциями прикладного слоя.
"""
from __future__ import annotations

from typing import Any, Optional

from pydantic import Field

from app.core.schemas import ApiModel

JsonDict = dict[str, Any]     # данные, которые интерфейс показывает как есть

# ── версии фонда ─────────────────────────────────────────────────────────────


class FundVersionOut(ApiModel):
    id: int
    valid_from: str
    status: str
    rev: int


class SnapshotCategoryOut(ApiModel):
    id: int
    code: str
    title: str
    kind_id: int
    weight: float
    escorted: bool
    sort_order: int


class SnapshotGroupOut(ApiModel):
    id: int
    parent_id: Optional[int]
    title: str
    sort_order: int
    escorted: bool
    path: list[int]


class SnapshotUnitOut(ApiModel):
    id: int
    label: str
    category_id: int
    group_id: Optional[int]
    floor: str
    flags: list[int]
    path: list[int]


class FundFlagOut(ApiModel):
    id: int
    title: str
    color: str
    sort_order: int
    archived: bool


class FundKindOut(ApiModel):
    id: int
    title: str
    sort_order: int
    expanded: bool
    archived: bool


class FundSnapshotOut(ApiModel):
    version: FundVersionOut
    categories: list[SnapshotCategoryOut]
    groups: list[SnapshotGroupOut]
    units: list[SnapshotUnitOut]
    flags: list[FundFlagOut]
    kinds: list[FundKindOut]


class FundVersionRowOut(ApiModel):
    id: int
    valid_from: str
    status: str
    author: Optional[str]
    note: Optional[str]
    published_at: Optional[str]


class DiffEntryOut(ApiModel):
    """Строка разницы фондов: что добавлено, изменено или выведено."""

    id: int
    kind: str
    before: JsonDict
    after: JsonDict
    from_: Optional[list[str]] = Field(None, alias="from")     # у нового объекта — из кого он получился


class FundDiffOut(ApiModel):
    categories: list[DiffEntryOut]
    groups: list[DiffEntryOut]
    units: list[DiffEntryOut]
    flags: list[DiffEntryOut]


class DraftOpenedOut(ApiModel):
    rev: Optional[int]
    id: int
    valid_from: str


class DraftMovedOut(ApiModel):
    rev: Optional[int]
    valid_from: str


class DraftEntityOut(ApiModel):
    rev: Optional[int]
    id: int


class DraftSplitOut(ApiModel):
    rev: Optional[int]
    ids: list[int]


class DraftRevOut(ApiModel):
    rev: Optional[int]


class IdOut(ApiModel):
    id: int


# ── предпросмотр и разница по броням ─────────────────────────────────────────


class ImpactDiffOut(ApiModel):
    """Что изменит операция в бронях: переезды, предупреждения, покрытие батлерами, нагрузка."""

    moved: list[JsonDict]
    warnings_added: list[JsonDict]
    warnings_removed: list[JsonDict]
    coverage_changes: list[JsonDict]
    load_changes: list[JsonDict]


class PublishedVersionOut(ApiModel):
    id: int
    valid_from: str
    rev: int


class PublishAffectedOut(ApiModel):
    moved: list[JsonDict]
    unassigned: list[JsonDict]
    pin_invalid: list[JsonDict]
    category_missing: list[JsonDict]


class PublishResultOut(ApiModel):
    version: PublishedVersionOut
    fund_diff: FundDiffOut
    propagated: list[JsonDict]
    kept: list[JsonDict]
    skipped: list[JsonDict]
    transfers: list[JsonDict]
    affected: PublishAffectedOut


class PublishOut(ApiModel):
    preview: bool
    result: PublishResultOut
    diff: ImpactDiffOut
    overbook_refused: Optional[str]


class DeleteVersionOut(ApiModel):
    preview: bool
    result: JsonDict
    diff: ImpactDiffOut
    overbook_refused: Optional[str]


# ── файл фонда ───────────────────────────────────────────────────────────────


class RetiredOut(ApiModel):
    entity: str
    id: int
    name: Optional[str]


class FlagChangesOut(ApiModel):
    created: list[JsonDict]
    renamed: list[JsonDict]
    recoloured: list[JsonDict]


class FundImportOut(ApiModel):
    id: int
    valid_from: str
    rev: int
    diff: FundDiffOut
    retired: list[RetiredOut]
    flags: FlagChangesOut


class ResetPreviewOut(ApiModel):
    counts: dict[str, int]
    will_load: dict[str, int]
    warnings: list[str]
    fingerprint: str


class ResetOut(ApiModel):
    backup: str
    backup_url: str
    deleted: dict[str, int]
    loaded: dict[str, int]


class InProductionOut(ApiModel):
    in_production: bool


# ── справочники шахматки ─────────────────────────────────────────────────────


class LabelOut(ApiModel):
    id: int
    title: str
    color: str


class CustomFieldOut(ApiModel):
    id: int
    target: str
    code: str
    title: str
    kind: str
    searchable: bool
    sort_order: int
    choices: list[str]


class EscortRowOut(ApiModel):
    employee_id: int
    name: str
    active: bool


class StaysSettingsOut(ApiModel):
    special_factor: Optional[float]
    daily_limit: float
    replacement_codes: str


class VipCodeOut(ApiModel):
    id: int
    code: str
    title: str
    escorted: bool
    factor: float
    sort_order: int
    archived: bool


class StaffRowOut(ApiModel):
    id: int
    name: str
    position: str


class StaysDirectoriesOut(ApiModel):
    labels: list[LabelOut]
    fields: list[CustomFieldOut]
    escorts: list[EscortRowOut]
    settings: StaysSettingsOut
    in_production: bool
    vip_codes: list[VipCodeOut]
    staff: Optional[list[StaffRowOut]]          # только тем, у кого stays.setup


class EscortChangedOut(ApiModel):
    employee_id: int
    active: bool


class EscortsSeededOut(ApiModel):
    added: int


# ── гости ────────────────────────────────────────────────────────────────────


class GuestLinkRowOut(ApiModel):
    """Связь гостя в его карточке."""

    id: int
    guest_id: int
    kind: str
    former: bool
    label: str
    name: str
    special: bool
    vip_code: str


class GuestVipCodeOut(ApiModel):
    id: int
    code: str
    title: str
    archived: bool


class SpecialDateOut(ApiModel):
    date: str
    what: str


class GuestCardOut(ApiModel):
    id: int
    last_name: str
    first_name: str
    middle_name: str
    phone: str
    phone_display: str
    email: str
    birth_date: Optional[str]
    gender: str
    special: bool
    vip_code_id: Optional[int]
    vip_code: Optional[GuestVipCodeOut]
    main_current: int                      # брони, куда дойдёт смена кода
    note: str
    external_id: Optional[str]
    source: str
    preferences: dict[str, str]
    special_dates: list[SpecialDateOut]
    fields: JsonDict
    links: list[GuestLinkRowOut]


class GuestPickOut(ApiModel):
    """Гость в подборе: без контактов и дат рождения."""

    id: int
    last_name: str
    first_name: str
    middle_name: str
    special: bool
    vip_code_id: Optional[int]
    vip_code: str
    short: str


class GuestTabRowOut(ApiModel):
    id: int
    name: str
    special: bool
    vip_code: str
    vip_code_archived: bool
    gender: str
    phone: str
    last_stay: Optional[str]
    stays: int


class GuestTabOut(ApiModel):
    total: int
    rows: list[GuestTabRowOut]


class GuestStayOut(ApiModel):
    reservation_id: int
    number: str
    role: str
    status: str
    status_title: str
    date_from: str
    date_to: str
    units: list[str]
    butlers: list[str]


class GuestPrefOut(ApiModel):
    kind: str
    ref_id: int
    priority: int
    title: str


class GuestPrefsSavedOut(ApiModel):
    preview: bool
    result: list[GuestPrefOut]
    diff: ImpactDiffOut
    overbook_refused: Optional[str]


class GuestUpdatedOut(ApiModel):
    preview: bool
    guest: GuestCardOut
    updated_reservations: int
    diff: Optional[ImpactDiffOut]            # только если менялся код и есть брони, куда он дойдёт
    overbook_refused: Optional[str]


class GuestMergedOut(ApiModel):
    preview: bool
    keep_id: int
    drop_id: int
    moves: JsonDict
    diff: ImpactDiffOut
    overbook_refused: Optional[str]


class GuestLinkCreatedOut(ApiModel):
    id: int
    guest_id: int
    ids: list[int]


class GuestLinkFormerOut(ApiModel):
    id: int
    former: bool


class FamilyPersonOut(ApiModel):
    id: int
    name: str
    gender: str
    special: bool
    vip_code: str
    phone: Optional[str]                     # телефон и дата рождения — только полный уровень
    birth_date: Optional[str]


class FamilyLinkOut(ApiModel):
    id: int
    kind: str
    a: int
    b: int
    former: bool


class FamilyKinOut(ApiModel):
    person_id: int
    title: str
    degree: int


class FamilyOut(ApiModel):
    people: list[FamilyPersonOut]
    parents: list[list[int]]
    spouses: list[list[Any]]                 # [a, b, бывшие]
    links: list[FamilyLinkOut]
    kin: list[FamilyKinOut]


# ── брони, группы, блоки, OOO ────────────────────────────────────────────────


class PreviewedOut[T](ApiModel):
    """Ответ операции с предпросмотром: что получилось (``result``) и что изменится в бронях
    (``diff``). ``overbook_refused`` — текст отказа, если новый овербукинг без права не сохранится
    (в предпросмотре; при сохранении отказ — 409)."""

    preview: bool
    result: T
    diff: ImpactDiffOut
    overbook_refused: Optional[str]


class ReservationOccupantOut(ApiModel):
    id: int
    guest_id: int
    date_from: str
    date_to: str
    role: str
    name: str
    special: bool
    vip_code_id: Optional[int]


class ReservationSegmentOut(ApiModel):
    index: int
    category_id: int
    start: str
    end: str
    unit_id: Optional[int]
    pinned: bool


class ReservationMoveOut(ApiModel):
    move_date: str
    category_id: int


class ReservationCompanionOut(ApiModel):
    kind: str
    description: str


class ReservationLogisticsOut(ApiModel):
    kind: str
    date: Optional[str]
    time: str
    description: str


class ReservationEscortOut(ApiModel):
    declined: bool
    reasons: list[str]
    required_nights: int
    rule_reasons: list[str]


class ReservationVipCodeOut(ApiModel):
    id: int
    code: str
    title: str
    archived: bool


class ReservationDocOut(ApiModel):
    """Документ брони для формы правки."""

    id: int
    version: int
    number: str
    status: str
    status_title: str
    check_in: str
    check_out: str
    early: bool
    late: bool
    category_id: int
    paid_category_id: int
    label_id: Optional[int]
    customer: str
    note: str
    escort_mode: str
    vip_code_id: Optional[int]
    vip_code: Optional[ReservationVipCodeOut]
    group_id: Optional[int]
    external_id: Optional[str]
    source: str
    fields: JsonDict
    moves: list[ReservationMoveOut]
    segments: list[ReservationSegmentOut]
    occupants: list[ReservationOccupantOut]
    companions: list[ReservationCompanionOut]
    logistics: list[ReservationLogisticsOut]
    warnings: list[Any]
    escort: ReservationEscortOut


class GroupJoinedOut(ApiModel):
    group_id: int


class StayGroupOut(ApiModel):
    id: int
    title: str


class CohabitCandidateOut(ApiModel):
    reservation_id: int
    number: str
    check_in: str
    check_out: str
    main_guest: str
    group_id: Optional[int]


class BookingLabelOut(ApiModel):
    title: str
    color: str


class BookingRowOut(ApiModel):
    id: int
    number: str
    status: str
    status_title: str
    check_in: str
    check_out: str
    nights: int
    early: bool
    late: bool
    category: str
    unit: str
    upgrade: str
    main_guest: str
    special: bool
    vip_code: str
    escort_mode: str
    label: Optional[BookingLabelOut]
    butlers: list[str]
    created_at: str


class BookingListOut(ApiModel):
    total: int
    rows: list[BookingRowOut]


class BlockTopOut(ApiModel):
    category_id: int
    code: str
    max: int


class BlockRowOut(ApiModel):
    id: int
    title: str
    start: str
    end: str
    nights: int
    placed: int
    missing: int
    short: bool
    top: list[BlockTopOut]
    created_at: str


class BlockListOut(ApiModel):
    total: int
    rows: list[BlockRowOut]


class BlockCardOut(ApiModel):
    id: int
    title: str
    start: str
    end: str
    version: int
    nights: int
    placed: int
    missing: int
    short: list[JsonDict]
    top: list[BlockTopOut]
    grid: dict[str, dict[str, int]]


class BlockSavedOut(ApiModel):
    id: int
    title: str
    start: str
    end: str
    version: int
    grid: dict[str, dict[str, int]]
    dropped: Optional[list[Any]]               # ночи вне новых дат (только при замене блока)


class DeletedOut(ApiModel):
    id: int
    deleted: bool


class OooSavedOut(ApiModel):
    id: int
    unit_id: int
    start: str
    end: str
    start_half: str
    end_half: str
    reason: str
    version: int


class OooRowOut(ApiModel):
    id: int
    unit_id: int
    unit: str
    category_id: Optional[int]
    category: str
    group: str
    start: str
    end: str
    start_half: str
    end_half: str
    reason: str
    author: str
    created_at: str
    version: int


class OooListOut(ApiModel):
    total: int
    rows: list[OooRowOut]


# ── виды шахматки, табло, «Мои гости», покрытие ──────────────────────────────


class UnitsBoardOut(ApiModel):
    """Шахматка объектов; поля внутри полос и объектов зависят от уровня видимости (§8)."""

    days: list[str]
    units: list[JsonDict]
    bars: list[JsonDict]
    holds: list[JsonDict]
    blocks: list[JsonDict]
    warnings: list[JsonDict]
    visibility: str


class ReservationCardOut(ApiModel):
    """Карточка брони; состав полей по уровню видимости, остальное — как в документе брони."""

    id: int
    version: int
    number: str
    status: str
    status_title: str
    check_in: str
    check_out: str
    early: bool
    late: bool
    category: str
    paid_category: str
    paid_category_id: int
    upgrade: str
    label: Optional[JsonDict]
    customer: Optional[str]                  # заказчик, примечание, поля, спутники и логистика — только полный уровень
    note: Optional[str]
    escort_mode: str
    escort: JsonDict
    vip_code: Optional[JsonDict]
    pref: Optional[Any]
    group_id: Optional[int]
    fields: Optional[JsonDict]
    segments: list[JsonDict]
    occupants: list[JsonDict]
    companions: Optional[list[JsonDict]]
    logistics: Optional[list[JsonDict]]
    coverage: list[JsonDict]
    mine: Optional[bool]                     # только батлеру: своя ли бронь


class ReservationHistoryOut(ApiModel):
    action: str
    actor: str
    title: str
    ts: str
    diff: JsonDict


class GuestFullCardOut(GuestCardOut):
    """Карточка гостя целиком — с историей проживаний."""

    stays: list[GuestStayOut]


class ButlersBoardOut(ApiModel):
    days: list[str]
    limit: float
    rows: list[JsonDict]


class DayTotalsOut(ApiModel):
    """Итоги табло. Уровень «загрузка» (без данных гостей) видит только первые пять."""

    arrivals: int
    departures: int
    in_house: int
    no_show: int
    overbooked: int
    covered: Optional[int]
    declined: Optional[int]
    need_replacement: Optional[int]
    not_required: Optional[int]
    special: Optional[int]
    uncovered: Optional[int]


class DayBoardOut(ApiModel):
    """Табло дня; в строках броней поля зависят от уровня видимости (§8)."""

    date: str
    visibility: str
    arrivals: list[JsonDict]
    departures: list[JsonDict]
    in_house: list[JsonDict]
    no_show: list[JsonDict]
    attention: list[JsonDict]
    totals: DayTotalsOut


class OccupancyOut(ApiModel):
    days: list[str]
    nodes: list[JsonDict]
    total: JsonDict


class MineTodayOut(ApiModel):
    date: str
    reservations: list[JsonDict]


class MineMonthLoadOut(ApiModel):
    day: str
    guests: int
    level: str
    value: float


class MineMonthOut(ApiModel):
    days: list[str]
    limit: float
    load: list[MineMonthLoadOut]
    rows: list[JsonDict]
    absences: list[str]                 # даты отсутствия по Графику


class MineGuestRowOut(ApiModel):
    guest_id: int
    name: str
    special: bool
    vip_code: str
    stays: int
    last_stay: Optional[str]
    next_stay: Optional[str]


class MineGuestsOut(ApiModel):
    total: int
    rows: list[MineGuestRowOut]


class MineGuestCardOut(GuestCardOut):
    """Профиль своего гостя и история проживаний с тем, кто его вёл."""

    history: list[JsonDict]


class CoverageWrittenOut(ApiModel):
    written: int


class CoverageLineOut(ApiModel):
    line_id: Optional[int]


class CoverageCandidateOut(ApiModel):
    employee_id: int
    name: str
    load_after: float
    knows_guest: bool
    same_place: bool
    note: str


class ReplacementRowOut(ApiModel):
    """Бронь, которой нужна подмена: батлер на смене с кодом отсутствия, и подобранные кандидаты."""

    day: str
    employee_id: int
    employee: str
    reservation_id: int
    group_id: Optional[int]
    number: str
    code: str
    unit: Optional[str]
    candidates: list[CoverageCandidateOut]
