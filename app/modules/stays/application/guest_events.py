"""Календарь дат доступных гостей и видимость их проживания в день события."""
from __future__ import annotations

import datetime as dt
from calendar import monthrange
from collections import defaultdict
from dataclasses import dataclass
from typing import Literal

from sqlalchemy import extract, or_, select
from sqlalchemy.orm import Session, load_only
from sqlalchemy.sql.selectable import SelectBase

from app.core.auth import Principal
from app.core.errors import Forbidden
from app.core.time import local_date
from app.modules.fund.application.fund import FundError
from app.modules.guests.application.catalog import Guest, GuestLink, VipCode
from app.modules.guests.application.guests import short_name

from ..adapters.orm import Occupant
from . import mine
from .context import load_context

EventKind = Literal["birthday", "wedding", "special"]
Presence = Literal["staying", "arrival", "checkout", "tentative", "none", "unavailable"]
CONFIRMED = {"staying", "arrival", "checkout"}
PRIORITY = {"tentative": 1, "checkout": 2, "arrival": 3, "staying": 4}
KIND_ORDER = {"birthday": 0, "wedding": 1, "special": 2}
WEDDING = "Годовщина свадьбы"


@dataclass(frozen=True)
class Occurrence:
    id: str
    date: dt.date
    kind: EventKind
    title: str
    guest_ids: tuple[int, ...]


@dataclass(frozen=True)
class Stay:
    status: Presence
    unit: str | None = None
    reservation_id: int | None = None


def _visible_guests(db: Session, scope: SelectBase | None) -> dict[int, Guest]:
    selected = select(Guest).options(load_only(
        Guest.id, Guest.last_name, Guest.first_name, Guest.birth_date, Guest.special_dates,
        Guest.special, Guest.vip_code_id,
    ))
    if scope is not None:
        selected = selected.where(Guest.id.in_(scope))
    return {guest.id: guest for guest in db.scalars(selected)}


def _yearly_date(source: dt.date, first: dt.date, last: dt.date) -> dt.date | None:
    # Как у особых дат в «Моих гостях»: 29 февраля в обычный год — 28 февраля.
    if source.month == first.month and source.year <= first.year:
        return first.replace(day=min(source.day, last.day))
    return None


def _weddings(db: Session, guests: dict[int, Guest], scope: SelectBase | None,
              first: dt.date, last: dt.date) -> list[Occurrence]:
    if not guests:
        return []
    date = GuestLink.marriage_start
    query = select(GuestLink.guest_a_id, GuestLink.guest_b_id, date).where(
        GuestLink.kind == "spouse", GuestLink.former.is_(False),
        date < first.replace(month=1), extract("month", date) == first.month,
    ).order_by(GuestLink.id)
    if scope is not None:
        owned = select(scope.cte("event_guest_ids").c.guest_id)
        query = query.where(or_(GuestLink.guest_a_id.in_(owned), GuestLink.guest_b_id.in_(owned)))
    links = db.execute(query)
    out = []
    for a, b, start in links:
        # Та же фактическая годовщина, что в блоке «Сейчас важно».
        if start is not None and start.day <= last.day:
            visible = tuple(i for i in (a, b) if i in guests)
            if visible:
                out.append(Occurrence(f"wedding:{min(visible)}", first.replace(day=start.day), "wedding", WEDDING, visible))
    return out


def _occurrences(db: Session, guests: dict[int, Guest], scope: SelectBase | None,
                 first: dt.date, last: dt.date, kind: EventKind | None) -> list[Occurrence]:
    weddings = [] if kind == "birthday" else _weddings(db, guests, scope, first, last)
    if kind == "wedding":
        return weddings
    structured = {(gid, e.date) for e in weddings for gid in e.guest_ids}
    out = weddings if kind is None else []
    for gid, guest in guests.items():
        if kind != "special" and guest.birth_date and (day := _yearly_date(guest.birth_date, first, last)):
            out.append(Occurrence(f"birthday:{gid}", day, "birthday", "День рождения", (gid,)))
        if kind == "birthday":
            continue
        for index, item in enumerate(guest.special_dates or []):
            try:
                source = dt.date.fromisoformat(item.get("date") or "")
            except (TypeError, ValueError, AttributeError):
                continue
            day = _yearly_date(source, first, last)
            title = str(item.get("what") or "").strip()
            if day is None or ((gid, day) in structured and title.casefold() == WEDDING.casefold()):
                continue
            out.append(Occurrence(f"special:{gid}:{index}", day, "special", title or "Особая дата", (gid,)))
    return out


def _occupant_status(occupant: Occupant, day: dt.date, tentative: bool) -> Presence:
    if tentative:
        return "tentative"
    if occupant.date_to == day:
        return "checkout"
    return "arrival" if occupant.date_from == day else "staying"


def _stays(db: Session, dates: dict[int, set[dt.date]], first: dt.date, last: dt.date,
           employee_id: int | None) -> dict[tuple[int, dt.date], Stay]:
    """Отбирает ночь гостя по покрытию этой же даты или вчерашней ночи для выезда."""
    if not dates:
        return {}
    ctx = load_context(db, first - dt.timedelta(days=1), last, None, fund_window_only=True,
                       scope_guest_ids=set(dates))
    best: dict[tuple[int, dt.date], Stay] = {}
    for rid, occupants in ctx.occ.items():
        for occupant in occupants:
            gid = occupant.guest_id
            for day in dates.get(gid, ()):
                if not occupant.date_from <= day <= occupant.date_to:
                    continue
                key = (gid, day)
                night = day - dt.timedelta(days=1) if day == occupant.date_to else day
                if employee_id is not None and employee_id not in ctx.cover(night).by_guest.get((rid, gid), ()):
                    continue
                status = _occupant_status(occupant, day, ctx.res[rid].status == "tentative")
                if key not in best or PRIORITY[status] > PRIORITY[best[key].status]:
                    best[key] = Stay(status, ctx.unit_label(ctx.unit_of(rid, night)[0], night), rid)
    return best


def calendar(db: Session, principal: Principal, month: dt.date | None, *, kind: EventKind | None,
             confirmed_only: bool, vip_code_ids: list[int], special: bool) -> dict:
    perms = principal.gate_permissions
    full = "stays.guests" in perms
    employee = principal.employee if "stays.mine" in perms else None
    employee_id: int | None = employee.id if employee is not None else None
    if not full and employee_id is None:
        raise Forbidden("Календарь доступен для своих гостей или с правом просмотра профилей")

    today = local_date()
    first = month or today.replace(day=1)
    if first.day != 1 or (first.year, first.month) in ((1, 1), (9999, 12)):
        raise FundError("Укажите первое число месяца")
    last = first.replace(day=monthrange(first.year, first.month)[1])
    global_stays = full and "stays.view" in perms
    scope = mine.guest_ids_query(employee_id) if not full and employee_id is not None else None
    guests = _visible_guests(db, scope)
    owned = set(guests) if scope is not None else set()
    if full and not global_stays and employee_id is not None:
        owned = mine.my_guest_ids(db, employee_id)
    used_codes = {guest.vip_code_id for guest in guests.values() if guest.vip_code_id is not None}
    code_query = select(VipCode).order_by(VipCode.sort_order, VipCode.code)
    if not full:
        code_query = code_query.where(VipCode.id.in_(used_codes))
    codes = list(db.scalars(code_query))
    code_text = {code.id: code.code for code in codes}
    vip_choices = [{"id": code.id, "code": code.code} for code in codes if not code.archived or code.id in used_codes]
    vip_ids = set(vip_code_ids)

    def matches(gid: int) -> bool:
        guest = guests[gid]
        return (not special or guest.special) and (not vip_ids or guest.vip_code_id in vip_ids)

    occurrences = [e for e in _occurrences(db, guests, scope, first, last, kind)
                   if any(matches(i) for i in e.guest_ids)]
    wanted: dict[int, set[dt.date]] = defaultdict(set)
    for occurrence in occurrences:
        for gid in occurrence.guest_ids:
            if global_stays or gid in owned:
                wanted[gid].add(occurrence.date)
    stays = _stays(db, wanted, first, last, None if global_stays else employee_id)
    # Ограниченная роль не может отличить отсутствие брони от недоступной брони.
    default_stay = Stay("none" if global_stays else "unavailable")
    card_allowed = "stays.view" in perms

    def person(gid: int, day: dt.date) -> dict:
        guest = guests[gid]
        stay = stays.get((gid, day), default_stay)
        return {"guest_id": gid, "name": short_name(guest), "status": stay.status, "unit": stay.unit,
                "reservation_id": stay.reservation_id if card_allowed else None,
                "vip_code": code_text.get(guest.vip_code_id or 0), "special": guest.special}

    events = []
    for e in sorted(occurrences, key=lambda e: (e.date, KIND_ORDER[e.kind], e.guest_ids, e.id)):
        people = [person(gid, e.date) for gid in e.guest_ids]
        if confirmed_only and not any(matches(p["guest_id"]) and p["status"] in CONFIRMED for p in people):
            continue
        events.append({"id": e.id, "date": e.date, "kind": e.kind, "title": e.title, "people": people})
    return {"month": first, "today": today, "filters": {"guest_details": True, "vip_codes": vip_choices}, "events": events}
