"""Модели ответов модуля «Табло».

Каждый ключ ответа присутствует всегда; значение, которого в данном случае нет, — ``None``.
Состав полей в видах зависит от уровня видимости (§8): то, чего уровню не положено, — ``None``.
"""
from __future__ import annotations

from typing import Any, Optional

from app.core.schemas import ApiModel
from app.modules.guests.application.guest_schemas import GuestCardOut, GuestPrefOut  # noqa: F401

JsonDict = dict[str, Any]


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
