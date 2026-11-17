"""Тела запросов к покрытию батлерами (§4.2, §4.5, §5)."""
from __future__ import annotations

import datetime as dt
from typing import Literal, Optional

from pydantic import BaseModel, Field

from .coverage import Scope

MAX_DAYS = 62


class ScopeIn(BaseModel):
    reservation_id: Optional[int] = None
    group_id: Optional[int] = None
    guest_ids: list[int] = []

    def scope(self) -> Scope:
        return Scope(self.reservation_id, self.group_id, frozenset(self.guest_ids))


class TemplateIn(ScopeIn):
    kind: Literal["pair", "single"]
    butlers: list[int]
    first: dt.date
    last: dt.date
    replace: bool = False


class DayIn(ScopeIn):
    day: dt.date
    employee_id: Optional[int] = None          # пусто — снять назначение дня
    overnight: bool = False
    comment: str = Field("", max_length=255)


class DayChoice(BaseModel):
    day: dt.date
    employee_id: Optional[int] = None


class DaysIn(ScopeIn):
    days: list[DayChoice] = Field(min_length=1, max_length=MAX_DAYS)


class AddShiftIn(BaseModel):
    employee_id: int
    day: dt.date
    shift_type_id: int
