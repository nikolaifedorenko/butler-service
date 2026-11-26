"""Модели ответов guests, которые нужны и другим модулям: карточка гостя и его пожелания (их отдаёт
и правка в stays, и чтение в board)."""
from __future__ import annotations

import datetime as dt
from typing import Any, Optional

from app.core.external import ExternalRef
from app.core.schemas import ApiModel

JsonDict = dict[str, Any]


class GuestLinkRowOut(ApiModel):
    """Связь гостя в его карточке."""

    id: int
    guest_id: int
    kind: str
    former: bool
    marriage_start: Optional[dt.date]
    marriage_end: Optional[dt.date]
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
    external: Optional[ExternalRef]
    preferences: dict[str, str]
    special_dates: list[SpecialDateOut]
    fields: JsonDict
    links: list[GuestLinkRowOut]


class GuestPrefOut(ApiModel):
    kind: str
    ref_id: int
    priority: int
    title: str
