"""Чтение видов «Шахматки» (§6): шахматка объектов, карточка брони. Загрузка пакетами —
число запросов не зависит от числа объектов и броней (бюджет SQL — §10)."""
from __future__ import annotations

import datetime as dt
import json
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.time import local_date

from ..adapters.orm import (
    Assignment,
    Category,
    Companion,
    Guest,
    Hold,
    Label,
    Logistics,
    Move,
    Occupant,
    Reservation,
    Unit,
)
from ..domain.allocate import natural_key
from ..domain.halfday import hold_span, segments
from ..ports.duty import DutyPort
from . import allocation
from .context import butlers_on, load_context, nights
from .guests import search_query, short_name
from .reservations import STATUS_TITLES
from .visibility import Level, at_least, serialize_bar

MAX_DAYS = 62
LEVEL_RANK = {"regular": 0, "vip": 1, "vvip": 2}


class ViewError(ValueError):
    """Ошибка параметров вида → 422."""


@dataclass(frozen=True)
class BoardFilters:
    kind: str | None = None
    building: str | None = None
    floor: str | None = None
    category_id: int | None = None
    escorted_only: bool = False
    vip: bool = False
    employee_id: int | None = None          # «кто ведёт» — с задачи 14
    q: str = ""


def check_window(first: dt.date, last: dt.date) -> list[dt.date]:
    if last < first:
        raise ViewError("Конец периода раньше начала")
    if (last - first).days + 1 > MAX_DAYS:
        raise ViewError(f"Период шахматки — не больше {MAX_DAYS} дней")
    return [first + dt.timedelta(days=i) for i in range((last - first).days + 1)]


def _d(v: dt.date | None) -> str | None:
    return v.isoformat() if v else None


def _top_level(levels) -> str:
    return max(levels, key=lambda lv: LEVEL_RANK[lv], default="regular")


def units_board(db: Session, first: dt.date, last: dt.date, f: BoardFilters, level: Level) -> dict:
    days = check_window(first, last)
    cats = {c.id: c for c in db.scalars(select(Category))}
    stmt = select(Unit).where(Unit.active.is_(True))
    if f.building:
        stmt = stmt.where(Unit.building == f.building)
    if f.floor:
        stmt = stmt.where(Unit.floor == f.floor)
    if f.category_id:
        stmt = stmt.where(Unit.category_id == f.category_id)
    units = [u for u in db.scalars(stmt)
             if (not f.kind or cats[u.category_id].kind == f.kind)
             and (not f.escorted_only or cats[u.category_id].escorted)]
    units.sort(key=lambda u: (cats[u.category_id].sort_order, natural_key(u.label)))
    unit_ids = {u.id for u in units}
    visible_cats = {u.category_id for u in units}

    res = list(db.scalars(select(Reservation).where(Reservation.status.in_(allocation.OCCUPYING),
                                                    Reservation.check_in <= last,
                                                    Reservation.check_out >= first)))
    rids = [r.id for r in res]
    moves: dict[int, list] = {rid: [] for rid in rids}
    asg: dict[tuple[int, int], int | None] = {}
    occ: dict[int, list[Occupant]] = {rid: [] for rid in rids}
    if rids:
        for m in db.scalars(select(Move).where(Move.reservation_id.in_(rids))):
            moves[m.reservation_id].append((m.move_date, m.category_id))
        for a in db.scalars(select(Assignment).where(Assignment.reservation_id.in_(rids))):
            asg[(a.reservation_id, a.seg_index)] = a.unit_id
        for o in db.scalars(select(Occupant).where(Occupant.reservation_id.in_(rids))
                            .order_by(Occupant.date_from, Occupant.id)):
            occ[o.reservation_id].append(o)
    names = level != "occupancy"
    guests = {}
    labels = {}
    if names:
        gids = {o.guest_id for os in occ.values() for o in os}
        guests = {g.id: g for g in db.scalars(select(Guest).where(Guest.id.in_(gids)))} if gids else {}
        labels = {lb.id: lb for lb in db.scalars(select(Label))}
    match = _search(f.q, res, occ, guests, units, asg) if names and f.q.strip() else None
    today = local_date()
    on_duty: dict[int, list[str]] = {}
    if names and first <= today <= last:
        on_duty = butlers_on(db, today, res, moves, asg, occ, guests, cats, {u.id: u for u in units})

    bars = []
    for r in res:
        if match is not None and r.id not in match:
            continue
        rocc = occ[r.id]
        top = _top_level(guests[o.guest_id].level for o in rocc if o.guest_id in guests)
        if names and f.vip and top == "regular":
            continue
        segs = segments(r.check_in, r.check_out, r.early, r.late, r.category_id, moves[r.id])
        mains = [o for o in rocc if o.role == "main"]
        on_day = max(r.check_in, first)
        main_now = next((o for o in mains if o.date_from <= on_day < o.date_to), mains[0] if mains else None)
        lb = labels.get(r.label_id)
        base = {"reservation_id": r.id, "status": r.status, "guests_count": len({o.guest_id for o in rocc}),
                "number": r.number, "label": {"title": lb.title, "color": lb.color} if lb else None,
                "main_guest": short_name(guests[main_now.guest_id]) if main_now and main_now.guest_id in guests else "",
                "mains": [{"guest": short_name(guests[o.guest_id]), "from": _d(o.date_from), "to": _d(o.date_to)}
                          for o in mains if o.guest_id in guests],
                "level": top, "butlers_today": on_duty.get(r.id, []),
                "customer": r.customer, "purpose": r.purpose, "paid_by": r.paid_by, "note": r.note,
                "declined_butler": r.declined_butler, "fields": json.loads(r.fields_json or "{}")}
        for s in segs:
            uid = asg.get((r.id, s.index))
            if uid not in unit_ids and not (uid is None and s.category_id in visible_cats):
                continue
            bars.append(serialize_bar({**base, "seg_index": s.index, "unit_id": uid, "category_id": s.category_id,
                                       "start": _d(s.start), "end": _d(s.end), "start_pos": s.start_pos,
                                       "end_pos": s.end_pos, "early": r.early and s.index == 0,
                                       "late": r.late and s.index == len(segs) - 1}, level))

    holds = [{"id": h.id, "unit_id": h.unit_id, "start": _d(h.start), "end": _d(h.end), "kind": h.kind,
              # название блока — свободный текст (в нём бывает фамилия): только с уровня names
              "title": h.title if names else "", **dict(zip(("start_pos", "end_pos"), hold_span(h.start, h.end), strict=True))}
             for h in db.scalars(select(Hold).where(Hold.start <= last, Hold.end >= first))
             if h.unit_id in unit_ids]
    warnings = []
    if names:
        state = allocation.current_state(db)
        shown = {b["reservation_id"] for b in bars}
        warnings = [{"kind": w.kind, "reservation_ids": state.members[w.key], "text": w.text}
                    for w in state.warnings if shown & set(state.members[w.key])]
    return {"days": [_d(d) for d in days], "visibility": level,
            "units": [{"id": u.id, "label": u.label, "category_id": u.category_id,
                       "category": cats[u.category_id].code, "kind": cats[u.category_id].kind,
                       "escorted": cats[u.category_id].escorted, "building": u.building, "floor": u.floor}
                      for u in units],
            "bars": bars, "holds": holds, "warnings": warnings}


def _search(q: str, res, occ, guests, units, asg) -> set[int]:
    needle = search_query(q)
    hits = {r.id for r in res if needle in (r.search_text or "")}
    hits |= {rid for rid, os in occ.items() if any(needle in (guests[o.guest_id].search_text or "")
                                                   for o in os if o.guest_id in guests)}
    unit_hit = {u.id for u in units if needle in u.label.lower()}
    hits |= {rid for (rid, _), uid in asg.items() if uid in unit_hit}
    return hits


def card_coverage(db: Session, r: Reservation, duty: DutyPort | None) -> list[dict]:
    """Покрытие брони по ночам: кто кого ведёт и предупреждения дня против Графика (§4.4)."""
    ctx = load_context(db, r.check_in, r.check_out - dt.timedelta(days=1), duty)
    out = []
    for d in nights(r.check_in, r.check_out):
        cover = ctx.cover(d)
        who: dict[int, list[int]] = {}
        for (rid, g), emps in cover.by_guest.items():
            if rid == r.id:
                for e in emps:
                    who.setdefault(e, []).append(g)
        lines = [ln for ln in ctx.lines_on(d) if ln.reservation_id == r.id
                 or (ln.group_id is not None and ln.group_id == r.group_id)]
        butlers = [{"employee_id": e, "name": ctx.name(e), "guest_ids": sorted(gs),
                    "line_id": next((ln.id for ln in lines if ln.employee_id == e), None),
                    "overnight": any(ln.overnight for ln in lines if ln.employee_id == e)}
                   for e, gs in sorted(who.items())]
        mine = set(who)
        warns = [{"kind": w.kind, "employee_id": w.employee_id, "text": ctx.warning_text(w)}
                 for w in ctx.warnings(d) if w.reservation_id == r.id
                 or (w.reservation_id is None and w.employee_id in mine)]
        out.append({"day": d.isoformat(), "butlers": butlers, "warnings": warns})
    return out


def reservation_card(db: Session, rid: int, level: Level, duty: DutyPort | None = None) -> dict:
    """Карточка брони (§6.5): уровень «с фамилиями» — состав по датам; «полный» — плюс
    заказчик, примечания, сопровождающие, логистика, настраиваемые поля."""
    r = db.get(Reservation, rid)
    if r is None:
        raise LookupError("Бронь не найдена")
    moves = sorted((m.move_date, m.category_id) for m in db.scalars(select(Move).where(Move.reservation_id == rid)))
    asg = {a.seg_index: a.unit_id for a in db.scalars(select(Assignment).where(Assignment.reservation_id == rid))}
    unit_labels = dict(db.execute(select(Unit.id, Unit.label)).all())
    occ = list(db.scalars(select(Occupant).where(Occupant.reservation_id == rid)
                          .order_by(Occupant.date_from, Occupant.id)))
    guests = {g.id: g for g in db.scalars(select(Guest).where(Guest.id.in_({o.guest_id for o in occ})))} if occ else {}
    lb = db.get(Label, r.label_id) if r.label_id else None
    card = {
        "id": r.id, "number": r.number, "status": r.status, "status_title": STATUS_TITLES[r.status],
        "check_in": _d(r.check_in), "check_out": _d(r.check_out), "early": r.early, "late": r.late,
        "category": db.get(Category, r.category_id).code, "label": {"title": lb.title, "color": lb.color} if lb else None,
        "group_id": r.group_id, "version": r.version,
        "segments": [{"index": s.index, "start": _d(s.start), "end": _d(s.end), "unit_id": asg.get(s.index),
                      "unit": unit_labels.get(asg.get(s.index))}
                     for s in segments(r.check_in, r.check_out, r.early, r.late, r.category_id, moves)],
        "occupants": [{"guest_id": o.guest_id, "guest": short_name(guests[o.guest_id]),
                       "level": guests[o.guest_id].level, "date_from": _d(o.date_from),
                       "date_to": _d(o.date_to), "role": o.role} for o in occ if o.guest_id in guests],
        "coverage": card_coverage(db, r, duty) if r.status in allocation.OCCUPYING else [
            {"day": d.isoformat(), "butlers": [], "warnings": []} for d in nights(r.check_in, r.check_out)],
    }
    if at_least(level, "full"):
        card |= {"customer": r.customer, "purpose": r.purpose, "paid_by": r.paid_by, "note": r.note,
                 "declined_butler": r.declined_butler, "fields": json.loads(r.fields_json or "{}"),
                 "companions": [{"kind": c.kind, "description": c.description} for c in
                                db.scalars(select(Companion).where(Companion.reservation_id == rid))],
                 "logistics": [{"kind": lg.kind, "date": _d(lg.date), "time": lg.time, "description": lg.description}
                               for lg in db.scalars(select(Logistics).where(Logistics.reservation_id == rid)
                                                    .order_by(Logistics.date, Logistics.id))]}
    return card


def occupancy_grid(db: Session, first: dt.date, last: dt.date, building: str | None) -> dict:
    """Сводная загрузка (§6.4): категории × дни — занято из всего, заезды, выезды, не заехали.
    Строится из шахматки уровня «без гостей» — данных гостей здесь нет по построению."""
    from ..domain.halfday import PM, pos
    days = check_window(first, last)
    board = units_board(db, first, last, BoardFilters(building=building), "occupancy")
    cats = {c.id: c for c in db.scalars(select(Category))}
    by_cat: dict[int, list[int]] = {}
    for u in board["units"]:
        by_cat.setdefault(u["category_id"], []).append(u["id"])
    no_show = list(db.scalars(select(Reservation).where(Reservation.status == "no_show",
                                                        Reservation.check_in >= first, Reservation.check_in <= last)))
    out = []
    for cid, uids in sorted(by_cat.items(), key=lambda x: (cats[x[0]].sort_order, cats[x[0]].code)):
        bars = [b for b in board["bars"] if b["unit_id"] in set(uids)]
        cells = []
        for d in days:
            p, iso = pos(d, PM), d.isoformat()
            cells.append({"day": iso, "busy": len({b["unit_id"] for b in bars if b["start_pos"] <= p <= b["end_pos"]}),
                          "arrivals": sum(1 for b in bars if b["start"] == iso and b["seg_index"] == 0),
                          "departures": len({b["reservation_id"] for b in bars if b["end"] == iso}),
                          "no_show": sum(1 for r in no_show if r.category_id == cid and r.check_in == d)})
        out.append({"category_id": cid, "code": cats[cid].code, "title": cats[cid].title, "total": len(uids),
                    "cells": cells})
    return {"days": [d.isoformat() for d in days], "categories": out}
