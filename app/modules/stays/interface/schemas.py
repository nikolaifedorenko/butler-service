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
