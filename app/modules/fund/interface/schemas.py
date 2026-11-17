"""Модели ответов модуля «Фонд».

Каждый ключ ответа присутствует всегда; значение, которого в данном случае нет, — ``None``.
Модели запросов лежат рядом с операциями прикладного слоя.
"""
from __future__ import annotations

from typing import Any, Optional

from app.core.schemas import ApiModel

from ..application.fund_schemas import FundDiffOut

JsonDict = dict[str, Any]


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


