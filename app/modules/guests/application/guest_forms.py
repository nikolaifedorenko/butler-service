"""Тела запросов к профилям гостей, связям, пожеланиям и объединению дублей."""
from __future__ import annotations

import datetime as dt
from typing import Literal, Optional

from pydantic import BaseModel, Field

from . import guests


class SpecialDate(BaseModel):
    date: dt.date
    what: str = Field(max_length=120)


class GuestIn(BaseModel):
    last_name: str = Field(min_length=1, max_length=80)
    first_name: str = Field("", max_length=80)
    middle_name: str = Field("", max_length=80)
    phone: str = Field("", max_length=40)
    email: str = Field("", max_length=120)
    birth_date: Optional[dt.date] = None
    gender: Literal["m", "f", ""] = ""
    special: bool = False
    vip_code_id: Optional[int] = None
    preferences: dict[str, str] = {}
    special_dates: list[SpecialDate] = []
    fields: dict = {}
    note: str = Field("", max_length=4000)


class GuestUpdateIn(GuestIn):
    """Правка профиля: сменился код — update_reservations переносит его в текущие и будущие
    брони, где гость главный (§3.1); по умолчанию — да."""
    update_reservations: bool = True


class NewGuestIn(BaseModel):
    last_name: str = Field(min_length=1, max_length=80)
    first_name: str = Field("", max_length=80)
    gender: Literal["m", "f", ""] = ""


class LinkIn(BaseModel):
    """parent — гость из пути родитель guest_id; former — бывшие супруги/партнёры. Вторая сторона —
    guest_id (существующий) или new_guest (создаётся в той же записи). other_is_parent — вторая
    сторона родитель гостя из пути; also_parent_id — второй родитель того же ребёнка;
    also_former_id — прежний брак гостя станет «бывшим» той же записью (новый супруг)."""
    guest_id: Optional[int] = None
    new_guest: Optional[NewGuestIn] = None
    kind: str
    former: bool = False
    other_is_parent: bool = False
    also_parent_id: Optional[int] = None
    expected_parent_ids: Optional[list[int]] = Field(None, max_length=2)
    also_former_id: Optional[int] = None


class FormerIn(BaseModel):
    """former — супруги бывшие (true) или действующие (false)."""
    former: bool


class PrefIn(BaseModel):
    """Пожелание к объекту: узел фонда, флаг или объект; priority — больше, важнее."""
    kind: Literal["group", "flag", "unit"]
    ref_id: int = Field(ge=1)
    priority: int = Field(1, ge=1, le=guests.MAX_PRIORITY)


class PrefsIn(BaseModel):
    prefs: list[PrefIn] = Field(max_length=guests.MAX_PREFS)


class MergeIn(BaseModel):
    """keep_id — кого оставить, drop_id — дубль, который удаляется."""
    keep_id: int
    drop_id: int
