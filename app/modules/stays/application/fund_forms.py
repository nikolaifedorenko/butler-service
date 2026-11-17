"""Тела запросов к фонду: версии, черновик, справочники флагов и видов.

Лежат рядом с операциями прикладного слоя: правила ввода (длины, цвет ``#RRGGBB``) — часть
операции, а не роутера.
"""
from __future__ import annotations

import datetime as dt
import re
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

SORT = Field(100, ge=-100_000, le=100_000)


class CategoryIn(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)

    code: str = Field(min_length=1, max_length=16)
    title: str = Field(min_length=1, max_length=120)
    kind_id: int                       # вид из справочника видов категорий
    escorted: bool = False
    weight: float = Field(ge=0, le=100)
    sort_order: int = SORT


class DraftIn(BaseModel):
    valid_from: dt.date
    note: str = Field("", max_length=500)


class DraftMoveIn(BaseModel):
    rev: int
    valid_from: dt.date


class TransferIn(BaseModel):
    reservation_id: int
    category_id: int


class PublishIn(BaseModel):
    rev: int
    propagate: bool = True                 # перенести правки в поздние версии (§4.4)
    transfers: list[TransferIn] = Field([], max_length=500)


class DraftCategoryIn(CategoryIn):
    rev: int


class DraftGroupIn(BaseModel):
    rev: int
    title: str = Field(min_length=1, max_length=120)
    parent_id: Optional[int] = None
    sort_order: int = SORT
    escorted: bool = False


class UnitFields(BaseModel):
    label: str = Field(min_length=1, max_length=40)
    category_id: int
    group_id: Optional[int] = None
    floor: str = Field("", max_length=8)


class DraftUnitIn(UnitFields):
    rev: int
    flags: list[int] = []


class PartIn(BaseModel):
    label: str = Field(min_length=1, max_length=40)
    category_id: Optional[int] = None
    group_id: Optional[int] = None
    floor: str = Field("", max_length=8)


class SplitIn(BaseModel):
    rev: int
    parts: list[PartIn] = Field(min_length=2, max_length=50)


class MergeIn(BaseModel):
    rev: int
    unit_ids: list[int] = Field(min_length=2, max_length=50)
    label: str = Field(min_length=1, max_length=40)
    category_id: Optional[int] = None
    group_id: Optional[int] = None
    floor: str = Field("", max_length=8)


class FlagValueIn(BaseModel):
    rev: int
    flag_id: int
    unit_ids: list[int] = Field(max_length=500)
    value: bool


class FlagIn(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)

    title: str = Field(min_length=1, max_length=80)
    color: str = "#3b6fd8"
    sort_order: int = SORT

    @field_validator("color")
    @classmethod
    def _hex(cls, v: str) -> str:
        if not re.fullmatch(r"#[0-9a-fA-F]{6}", v):
            raise ValueError("Цвет в формате #RRGGBB")
        return v


class KindIn(BaseModel):
    title: str = Field(min_length=1, max_length=40)
    sort_order: int = SORT
    expanded: bool = False


class ArchiveIn(BaseModel):
    archived: bool


class InProductionIn(BaseModel):
    value: bool


class LabelIn(BaseModel):
    title: str = Field(min_length=1, max_length=80)
    color: str

    @field_validator("color")
    @classmethod
    def _hex(cls, v: str) -> str:
        if not re.fullmatch(r"#[0-9a-fA-F]{6}", v):
            raise ValueError("Цвет в формате #RRGGBB")
        return v


class FieldIn(BaseModel):
    target: Literal["guest", "reservation"]
    code: str = Field(min_length=1, max_length=32, pattern=r"^[A-Za-z][A-Za-z0-9_]*$")
    title: str = Field(min_length=1, max_length=120)
    kind: Literal["text", "choice", "bool", "date"]
    choices: list[str] = []
    searchable: bool = False
    sort_order: int = SORT


class EscortIn(BaseModel):
    active: bool


class VipCodeIn(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)

    code: str = Field(max_length=8)           # цифры 1–8: остальное проверяет vip_codes.normalize_code
    title: str = Field("", max_length=80)
    escorted: bool = False
    factor: float = Field(1.0, ge=0.1, le=99)
    sort_order: int = SORT


class VipCodeArchiveIn(BaseModel):
    archived: bool


class SeedIn(BaseModel):
    position: str = Field("батлер", min_length=2, max_length=60)


class SettingsIn(BaseModel):
    # колонки Numeric(5,2): больше 999.99 PostgreSQL не примет; NaN сломал бы сравнения с лимитом
    model_config = ConfigDict(allow_inf_nan=False)

    special_factor: Optional[float] = Field(None, ge=0.1, le=99)
    daily_limit: float = Field(le=999)
    replacement_codes: str = Field("", max_length=120)
