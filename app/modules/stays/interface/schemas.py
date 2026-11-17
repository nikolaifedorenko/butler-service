"""Модели ответов модуля «Шахматка».

Каждый ключ ответа присутствует всегда; значение, которого в данном случае нет, — ``None``.
Модели запросов лежат рядом с операциями прикладного слоя.
"""
from __future__ import annotations

from typing import Any, Optional

from app.core.schemas import ApiModel
from app.modules.fund.application.fund_schemas import FundDiffOut
from app.modules.guests.application.guest_schemas import GuestCardOut, GuestPrefOut

JsonDict = dict[str, Any]     # данные, которые интерфейс показывает как есть

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
