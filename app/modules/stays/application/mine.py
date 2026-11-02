"""«Мои гости» и правка своих броней и гостей батлером (часть 4 §2–§4: stays.mine,
stays.mine_guest_edit, stays.mine_res_edit).

«Своя» бронь — та, где у батлера есть строка покрытия (на бронь или на её группу) за всё время:
в прошлом, сейчас, в будущем, в том числе на подмене; предварительные — тоже. «Свой» гость — тот,
кого батлер ведёт хоть одну ночь (явный список гостей сильнее строки «вся бронь / группа», как в
domain/coverage.resolve_day), или кого он сам завёл через семейное дерево. Батлер меняет только
состав (проживающих, кроме главного), логистику, сопровождающих, примечание и настраиваемые
поля; в профиле своих гостей — предпочтения, особые даты, поля и примечание. Принадлежность
проверяется на каждом запросе."""
from __future__ import annotations

import datetime as dt
import json

from sqlalchemy import and_, exists, or_, select, union
from sqlalchemy.orm import Session, aliased

from app.core.time import local_date

from ..adapters.orm import (
    Companion,
    CoverageGuest,
    CoverageLine,
    Guest,
    GuestLink,
    Logistics,
    Occupant,
    Reservation,
)
from . import allocation, family
from .context import load_context
from .fund import FundError
from .guests import format_phone, search_guests, short_name

LOCKED = ("number", "check_in", "check_out", "early", "late", "category_id", "label_id", "customer",
          "paid_category_id", "escort_mode", "vip_code_id", "group_id")
GUEST_FREE = ("preferences", "special_dates", "fields", "note")
MINE_TEXT = "Батлер может менять только состав, логистику и сведения о гостях"


class MineForbidden(FundError):
    """Чужая бронь или поле, которое батлеру менять нельзя → 403."""


def _targets(line, res):
    """Строка покрытия относится к брони: прямо или через группу, где у брони в этот день ночь."""
    return or_(res.id == line.reservation_id,
               and_(line.group_id.is_not(None), res.group_id == line.group_id,
                    res.check_in <= line.day, line.day < res.check_out))


def _my_line_res(employee_id: int):
    """(строка батлера, бронь, к которой она относится) — за всё время."""
    ln, r = aliased(CoverageLine), aliased(Reservation)
    q = (select(ln, r).join(r, _targets(ln, r))
         .where(ln.employee_id == employee_id, r.status.in_(allocation.OCCUPYING)))
    return q, ln, r


def my_reservation_ids(db: Session, employee_id: int) -> set[int]:
    q, _ln, r = _my_line_res(employee_id)
    return set(db.scalars(q.with_only_columns(r.id).distinct()))


def _guest_ids_query(employee_id: int):
    """Гости явных списков батлера; проживающие ночи, которую батлер ведёт строкой «вся бронь /
    группа», если в ту ночь их явно не ведёт другая строка (по брони или её группе); профили,
    которые батлер завёл сам."""
    q, ln, r = _my_line_res(employee_id)
    o, x = aliased(Occupant), aliased(CoverageLine)
    explicit = (select(CoverageGuest.guest_id).join(CoverageLine, CoverageLine.id == CoverageGuest.coverage_id)
                .where(CoverageLine.employee_id == employee_id))
    whole = (q.with_only_columns(o.guest_id)
             .join(o, and_(o.reservation_id == r.id, o.date_from <= ln.day, ln.day < o.date_to))
             .where(~exists().where(CoverageGuest.coverage_id == ln.id),
                    ~select(x.id).join(CoverageGuest, CoverageGuest.coverage_id == x.id).where(
                        x.day == ln.day, CoverageGuest.guest_id == o.guest_id,
                        or_(x.reservation_id == r.id, and_(x.group_id.is_not(None), x.group_id == r.group_id)))
                    .exists()))
    created = select(Guest.id).where(Guest.created_by_employee_id == employee_id)
    return union(explicit, whole, created)


def my_guest_ids(db: Session, employee_id: int) -> set[int]:
    return set(db.scalars(_guest_ids_query(employee_id)))


def search_my_guests(db: Session, employee_id: int, q: str) -> list[Guest]:
    """Подбор гостя среди своих (редактор связей батлера): связать можно только своих (§3)."""
    return search_guests(db, q, within=_guest_ids_query(employee_id))


def owns_reservation(db: Session, employee_id: int, reservation_id: int) -> bool:
    q, _ln, r = _my_line_res(employee_id)
    return db.scalar(select(exists(q.where(r.id == reservation_id)))) or False


def owns_guest(db: Session, employee_id: int, guest_id: int) -> bool:
    return db.scalar(select(Guest.id).where(Guest.id == guest_id,
                                            Guest.id.in_(_guest_ids_query(employee_id)))) is not None


def _iso(v):
    return v.isoformat() if isinstance(v, dt.date) else v


def check_reservation_change(db: Session, before: dict, doc: dict) -> None:
    """Сравнить документ батлера с текущим: запертые поля, переезды, закрепления, главный гость;
    новый проживающий — родственник кого-то из прежних проживающих по семейному дереву (в том
    числе вычисленный, domain/kinship) или его прямая связь любого вида (§3) — иначе так можно
    было бы открыть себе профиль любого гостя."""
    def locked(d: dict, k: str):
        # пустая «оплата за» — категория брони
        return _iso(d.get(k) or d.get("category_id")) if k == "paid_category_id" else _iso(d.get(k))
    if any(locked(doc, k) != locked(before, k) for k in LOCKED):
        raise MineForbidden(MINE_TEXT)
    if [(_iso(m["move_date"]), m["category_id"]) for m in doc["moves"]] != \
            [(m["move_date"], m["category_id"]) for m in before["moves"]]:
        raise MineForbidden(MINE_TEXT)
    if doc.get("pins"):
        raise MineForbidden(MINE_TEXT)

    def mains(occ):
        return sorted((o["guest_id"], _iso(o["date_from"]), _iso(o["date_to"])) for o in occ if o["role"] == "main")
    if mains(doc["occupants"]) != mains(before["occupants"]):
        raise MineForbidden(MINE_TEXT)
    had = {o["guest_id"] for o in before["occupants"]}
    new = {o["guest_id"] for o in doc["occupants"]} - had
    if not new:
        return
    linked = set()
    for a, b in db.execute(select(GuestLink.guest_a_id, GuestLink.guest_b_id).where(
            (GuestLink.guest_a_id.in_(had) & GuestLink.guest_b_id.in_(new))
            | (GuestLink.guest_b_id.in_(had) & GuestLink.guest_a_id.in_(new)))):
        linked |= {a, b}
    rest = new - linked
    if rest and not rest <= family.relatives_among(db, had, rest):
        raise MineForbidden("Батлер добавляет только родственников и связанных с проживающими брони")


def check_link_change(db: Session, employee_id: int, link: GuestLink) -> None:
    """Удалить связь или отметить «бывших» батлер может, если хотя бы одна её сторона — свой гость."""
    if not any(owns_guest(db, employee_id, g) for g in (link.guest_a_id, link.guest_b_id)):
        raise MineForbidden("Это связь чужих гостей: вы не ведёте ни одного из них")


def check_guest_change(before: dict, data: dict) -> None:
    for k, v in data.items():
        if k in GUEST_FREE:
            continue
        old = before.get("phone") if k == "phone" else before.get(k)
        if k == "phone":
            from .guests import normalize_phone
            v = normalize_phone(v)
        if _iso(v) != _iso(old) and not (v in ("", None) and old in ("", None)):
            raise MineForbidden(MINE_TEXT)


def my_guests(db: Session, employee_id: int) -> dict:
    """Экран «Мои гости» до задач 4–5: свои брони, которые живут со вчера до +7 дней, и дни, когда
    батлер ведёт их гостей."""
    today = local_date()
    first, last = today - dt.timedelta(days=1), today + dt.timedelta(days=7)
    q, line, booking = _my_line_res(employee_id)
    owned: dict[int, set[dt.date]] = {}
    for rid, day in db.execute(q.with_only_columns(booking.id, line.day)
                               .where(booking.check_out >= first, booking.check_in <= last)):
        owned.setdefault(rid, set()).add(day)
    if not owned:
        return {"reservations": []}
    ctx = load_context(db, first, last, None)
    res = {r.id: r for r in db.scalars(select(Reservation).where(Reservation.id.in_(list(owned))))}
    logistics: dict[int, list] = {}
    for lg in db.scalars(select(Logistics).where(Logistics.reservation_id.in_(list(owned)))
                         .order_by(Logistics.date, Logistics.time)):
        logistics.setdefault(lg.reservation_id, []).append({"kind": lg.kind, "date": _iso(lg.date), "time": lg.time,
                                                            "description": lg.description})
    companions: dict[int, list] = {}
    for c in db.scalars(select(Companion).where(Companion.reservation_id.in_(list(owned)))):
        companions.setdefault(c.reservation_id, []).append({"kind": c.kind, "description": c.description})
    occ = list(db.scalars(select(Occupant).where(Occupant.reservation_id.in_(list(owned)))))
    out = []
    for rid, days in sorted(owned.items(), key=lambda x: min(x[1])):
        r = res[rid]
        units = [ctx.unit_label(ctx.unit_of(rid, d)[0], d) for d in sorted(days) if rid in ctx.res]
        guests = []
        for o in sorted((o for o in occ if o.reservation_id == rid), key=lambda o: (o.role != "main", o.id)):
            g = ctx.guests.get(o.guest_id)
            if g is None:
                continue
            guests.append({"guest_id": g.id, "name": short_name(g), "special": bool(g.special), "role": o.role,
                           "date_from": _iso(o.date_from), "date_to": _iso(o.date_to),
                           "phone": format_phone(g.phone), "preferences": json.loads(g.preferences_json or "{}"),
                           "special_dates": json.loads(g.special_dates_json or "[]")})
        out.append({"reservation_id": rid, "number": r.number, "status": r.status, "check_in": _iso(r.check_in),
                    "check_out": _iso(r.check_out), "units": list(dict.fromkeys(units)),
                    "days": sorted(d.isoformat() for d in days), "guests": guests, "note": r.note,
                    "logistics": logistics.get(rid, []), "companions": companions.get(rid, [])})
    return {"reservations": out}
