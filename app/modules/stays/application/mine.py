"""«Мои гости» и правка своих броней батлером (§1 «Допущения», §6.6, §7 stays.edit_mine).

«Свои» — брони, где батлер ведёт гостей сегодня и 7 дней вперёд, и где вёл вчера (дописать
после выезда). Батлер меняет только состав (проживающих, кроме главного), логистику,
сопровождающих, примечание и настраиваемые поля; в профиле своих гостей — предпочтения,
особые даты, поля и примечание. Принадлежность проверяется на каждом запросе."""
from __future__ import annotations

import datetime as dt
import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.time import local_date

from ..adapters.orm import Companion, CoverageLine, GuestLink, Logistics, Occupant, Reservation
from . import allocation
from .context import load_context
from .fund import FundError
from .guests import format_phone, short_name

LOCKED = ("number", "check_in", "check_out", "early", "late", "category_id", "label_id", "customer",
          "paid_category_id", "declined_butler", "group_id")
GUEST_FREE = ("preferences", "special_dates", "fields", "note")
MINE_TEXT = "Батлер может менять только состав, логистику и сведения о гостях"


class MineForbidden(FundError):
    """Чужая бронь или поле, которое батлеру менять нельзя → 403."""


def window(today: dt.date) -> tuple[dt.date, dt.date]:
    return today - dt.timedelta(days=1), today + dt.timedelta(days=7)


def _my_lines(db: Session, employee_id: int, today: dt.date) -> list[tuple[CoverageLine, Reservation]]:
    """Строки батлера по броням, которые живут в окне или выехали не раньше вчера —
    вместе с броней (для группы — каждый член, у которого в день строки есть ночь)."""
    first, last = window(today)
    live = (Reservation.status.in_(allocation.OCCUPYING), Reservation.check_out >= first,
            Reservation.check_in <= last)
    out = [(ln, r) for ln, r in db.execute(select(CoverageLine, Reservation).join(
        Reservation, Reservation.id == CoverageLine.reservation_id).where(CoverageLine.employee_id == employee_id, *live))]
    out += [(ln, r) for ln, r in db.execute(select(CoverageLine, Reservation).join(
        Reservation, Reservation.group_id == CoverageLine.group_id).where(CoverageLine.employee_id == employee_id, *live))
        if r.check_in <= ln.day < r.check_out]
    return out


def owned_reservations(db: Session, employee_id: int, today: dt.date | None = None) -> dict[int, set[dt.date]]:
    """Бронь → дни, когда батлер ведёт её гостей. «Своя» — ведёт в окне [вчера; +7] или вёл
    раньше, а выезд был не раньше вчера (дописать после выезда, §1 «Допущения»)."""
    today = today or local_date()
    first, last = window(today)
    out: dict[int, set[dt.date]] = {}
    for ln, r in _my_lines(db, employee_id, today):
        if first <= ln.day <= last or r.check_out >= first:
            out.setdefault(r.id, set()).add(ln.day)
    return out


def owns_guest(db: Session, employee_id: int, guest_id: int) -> bool:
    """Свой гость — тот, кого батлер фактически ведёт хоть одну ночь своих броней: строка
    «по гостям» другого батлера сильнее его строки «вся бронь» (§4.2)."""
    days = sorted({d for ds in owned_reservations(db, employee_id).values() for d in ds})
    if not days:
        return False
    ctx = load_context(db, days[0], days[-1], None)
    return any(employee_id in emps and g == guest_id
               for d in days for (_rid, g), emps in ctx.cover(d).by_guest.items())


def _iso(v):
    return v.isoformat() if isinstance(v, dt.date) else v


def check_reservation_change(db: Session, before: dict, doc: dict) -> None:
    """Сравнить документ батлера с текущим: запертые поля, переезды, закрепления, главный гость;
    новые проживающие — только связанные «кто кому» с гостями этой брони (иначе так можно
    было бы открыть себе профиль любого гостя)."""
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
    if new:
        linked = set()
        for a, b in db.execute(select(GuestLink.guest_a_id, GuestLink.guest_b_id).where(
                (GuestLink.guest_a_id.in_(had) & GuestLink.guest_b_id.in_(new))
                | (GuestLink.guest_b_id.in_(had) & GuestLink.guest_a_id.in_(new)))):
            linked |= {a, b}
        if not new <= linked:
            raise MineForbidden("Батлер добавляет только гостей, связанных с проживающими брони")


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
    today = local_date()
    owned = owned_reservations(db, employee_id, today)
    if not owned:
        return {"reservations": []}
    first, last = window(today)
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
            guests.append({"guest_id": g.id, "name": short_name(g), "level": g.level, "role": o.role,
                           "date_from": _iso(o.date_from), "date_to": _iso(o.date_to),
                           "phone": format_phone(g.phone), "preferences": json.loads(g.preferences_json or "{}"),
                           "special_dates": json.loads(g.special_dates_json or "[]")})
        out.append({"reservation_id": rid, "number": r.number, "status": r.status, "check_in": _iso(r.check_in),
                    "check_out": _iso(r.check_out), "units": list(dict.fromkeys(units)),
                    "days": sorted(d.isoformat() for d in days), "guests": guests, "note": r.note,
                    "logistics": logistics.get(rid, []), "companions": companions.get(rid, [])})
    return {"reservations": out}
