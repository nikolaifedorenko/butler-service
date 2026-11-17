"""Тела запросов к броням и группам совместного проживания."""
from __future__ import annotations

import datetime as dt
from typing import Literal, Optional

from pydantic import BaseModel, Field


class MoveIn(BaseModel):
    move_date: dt.date
    category_id: int


class OccupantIn(BaseModel):
    id: Optional[int] = None
    guest_id: int
    date_from: dt.date
    date_to: dt.date
    role: Literal["main", "guest"] = "guest"


class CompanionIn(BaseModel):
    kind: str = "other"
    description: str = Field("", max_length=255)


class LogisticsIn(BaseModel):
    kind: str = "transfer"
    date: Optional[dt.date] = None
    time: str = Field("", pattern=r"^(|\d{2}:\d{2})$")
    description: str = Field("", max_length=255)


class ReservationIn(BaseModel):
    number: str = Field("", max_length=40)
    status: Literal["tentative", "confirmed"] = "confirmed"     # только при создании
    check_in: dt.date
    check_out: dt.date
    early: bool = False
    late: bool = False
    category_id: int
    paid_category_id: Optional[int] = None                       # пусто — категория брони
    label_id: Optional[int] = None
    customer: str = Field("", max_length=160)
    note: str = Field("", max_length=4000)
    escort_mode: Literal["rules", "required", "declined"] = "rules"      # ручная отметка главнее правил
    vip_code_id: Optional[int] = None            # пусто при создании — из профиля главного гостя
    fields: dict = {}
    group_id: Optional[int] = None
    moves: list[MoveIn] = []
    occupants: list[OccupantIn] = []
    companions: list[CompanionIn] = []
    logistics: list[LogisticsIn] = []
    pins: Optional[dict[int, Optional[int]]] = None              # сегмент → объект; None — «авто»
    version: Optional[int] = None                                 # обязательна при правке


class StatusIn(BaseModel):
    status: str
    version: int
    new_check_in: Optional[dt.date] = None


class GroupIn(BaseModel):
    title: str = Field("", max_length=120)


class JoinIn(BaseModel):
    reservation_ids: list[int] = Field(min_length=2, max_length=10)


class LeaveIn(BaseModel):
    reservation_id: int
