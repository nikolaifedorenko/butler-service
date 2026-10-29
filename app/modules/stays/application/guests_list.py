"""Вкладка «Гости» (спека addendum §3): справочник гостей — ФИО, уровень, телефон (только полный
уровень), последний заезд, число проживаний; поиск по ФИО, телефону и номеру брони, фильтры
«уровень», «был в периоде», «день рождения в ближайшие N дней», сортировка на сервере, по 200.
Два запроса: гости и записи «проживающий» с номером и статусом брони; остальное — в памяти."""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.time import local_date

from ..adapters.orm import Guest, Occupant, Reservation
from .family import full_name
from .guests import LEVELS, GuestError, format_phone, guest_text, search_query
from .views import LEVEL_RANK
from .visibility import Level, at_least

SORTS = ("name", "level", "last_stay", "stays")
MAX_LIMIT = 200
MAX_BIRTHDAY_DAYS = 366
NOT_STAYED = ("cancelled", "no_show")      # такие брони — не проживание: ни в счётчике, ни в периоде


@dataclass(frozen=True)
class GuestQuery:
    q: str = ""
    level: str = ""                        # пусто — все уровни
    stayed_from: dt.date | None = None
    stayed_to: dt.date | None = None
    birthday_days: int | None = None
    sort: str = "name"
    dir: Literal["asc", "desc"] = "asc"
    offset: int = 0
    limit: int = MAX_LIMIT

    def __post_init__(self) -> None:
        if self.level and self.level not in LEVELS:
            raise GuestError("Уровень гостя: обычный, VIP или VVIP")
        if self.stayed_from and self.stayed_to and self.stayed_to < self.stayed_from:
            raise GuestError("Конец периода раньше начала")
        if self.birthday_days is not None and not 0 <= self.birthday_days <= MAX_BIRTHDAY_DAYS:
            raise GuestError(f"День рождения — в ближайшие 0…{MAX_BIRTHDAY_DAYS} дней")
        if self.sort not in SORTS:
            raise GuestError("Неизвестная колонка сортировки")
        if self.dir not in ("asc", "desc"):
            raise GuestError("Направление сортировки — asc или desc")
        if self.offset < 0 or not 1 <= self.limit <= MAX_LIMIT:
            raise GuestError(f"limit — от 1 до {MAX_LIMIT}, offset — не меньше 0")


@dataclass
class _Stays:
    """Проживания гостя: брони (без отменённых), ночи [с, по), номера всех его броней."""
    rids: set[int] = field(default_factory=set)
    spans: list[tuple[dt.date, dt.date]] = field(default_factory=list)
    numbers: set[str] = field(default_factory=set)

    @property
    def last(self) -> dt.date | None:
        return max((a for a, _ in self.spans), default=None)


def days_to_birthday(birth: dt.date, today: dt.date) -> int:
    """Через сколько дней ближайший день рождения (сегодня — 0); 29 февраля в невисокосный
    год — 28 февраля."""
    for year in (today.year, today.year + 1):
        try:
            d = birth.replace(year=year)
        except ValueError:
            d = dt.date(year, 2, 28)
        if d >= today:
            return (d - today).days
    raise AssertionError("недостижимо")          # pragma: no cover


def _stays(db: Session) -> dict[int, _Stays]:
    out: dict[int, _Stays] = {}
    for gid, rid, a, b, number, status in db.execute(
            select(Occupant.guest_id, Occupant.reservation_id, Occupant.date_from, Occupant.date_to,
                   Reservation.number, Reservation.status).join(Reservation, Reservation.id == Occupant.reservation_id)):
        s = out.setdefault(gid, _Stays())
        if number:
            s.numbers.add(number.lower())
        if status not in NOT_STAYED:
            s.rids.add(rid)
            s.spans.append((a, b))
    return out


def _sort_key(sort: str, stays: dict[int, _Stays]):
    empty = _Stays()
    return {
        "name": lambda g: (g.last_name.lower(), g.first_name.lower(), g.middle_name.lower()),
        "level": lambda g: LEVEL_RANK.get(g.level, 0),
        "last_stay": lambda g: stays.get(g.id, empty).last or dt.date.min,
        "stays": lambda g: len(stays.get(g.id, empty).rids),
    }[sort]


def find_guests(db: Session, q: GuestQuery, level: Level, today: dt.date | None = None) -> list[dict]:
    """Все подходящие гости в порядке сортировки (без среза страницы). Без полного уровня
    телефон не отдаётся и не ищется, а фильтр по дню рождения — PermissionError (иначе ответ
    выдавал бы дату рождения)."""
    if not at_least(level, "names"):
        raise PermissionError("Справочник гостей — с уровня «с фамилиями»")
    full = level == "full"
    if q.birthday_days is not None and not full:
        raise PermissionError("Фильтр по дню рождения — только с правом «Профили гостей целиком»")
    stmt = select(Guest)
    if q.level:
        stmt = stmt.where(Guest.level == q.level)
    guests = list(db.scalars(stmt))
    stays = _stays(db)
    empty = _Stays()
    needle = search_query(q.q) if q.q.strip() else ""
    if needle:
        guests = [g for g in guests if needle in guest_text(g, full)
                  or any(needle in n for n in stays.get(g.id, empty).numbers)]
    if q.stayed_from or q.stayed_to:
        lo, hi = q.stayed_from or dt.date.min, q.stayed_to or dt.date.max
        guests = [g for g in guests if any(a <= hi and b > lo for a, b in stays.get(g.id, empty).spans)]
    if q.birthday_days is not None:
        today = today or local_date()
        guests = [g for g in guests if g.birth_date and days_to_birthday(g.birth_date, today) <= q.birthday_days]
    # вторичные ключи — имя, затем id — всегда по возрастанию (устойчивая сортировка)
    guests.sort(key=lambda g: (*_sort_key("name", stays)(g), g.id))
    guests.sort(key=_sort_key(q.sort, stays), reverse=q.dir == "desc")
    rows = []
    for g in guests:
        s = stays.get(g.id, empty)
        row = {"id": g.id, "name": full_name(g), "level": g.level, "gender": g.gender}
        if full:
            row["phone"] = format_phone(g.phone)
        rows.append(row | {"last_stay": s.last.isoformat() if s.last else None, "stays": len(s.rids)})
    return rows


def list_guests(db: Session, q: GuestQuery, level: Level) -> dict:
    rows = find_guests(db, q, level)
    return {"total": len(rows), "rows": rows[q.offset:q.offset + q.limit]}
