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
