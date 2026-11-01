"""Шахматка батлеров и табло дня (§6.2, §6.3): всё из одного контекста покрытия, против
актуального Графика; кандидаты на табло — из того же контекста, «знает гостя» — одним
пакетом на день (бюджет SQL, §10)."""
from __future__ import annotations

import datetime as dt
import json
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..adapters.orm import Companion, Logistics, Ooo, Reservation
from ..domain.types import OFF, StayDay
from ..ports.duty import DutyPort
from .context import NO_GUESTS, StaysContext, load_context
from .coverage import _known, rank_in_ctx
from .family import kin_among
from .guests import search_query
from .views import fund_match
from .visibility import Level


def butlers_board(db: Session, first: dt.date, last: dt.date, duty: DutyPort) -> dict:
    ctx = load_context(db, first, last, duty)
    people = sorted(set(ctx.escorts) | {ln.employee_id for ln in ctx.lines}, key=lambda e: ctx.name(e))
    rows = []
    for e in people:
        cells = []
        for d in ctx.days():
            st = ctx.duty.get((e, d), OFF)
            by_res = {s.reservation_id: s for s in ctx.stays_on(d)}
            units, guests = [], []
            for (rid, g), emps in ctx.cover(d).by_guest.items():
                if e in emps:
                    label = ctx.unit_label(by_res[rid].unit_id, d)
                    if label not in [u["label"] for u in units]:
                        units.append({"label": label, "reservation_id": rid})
                    if g != NO_GUESTS:
                        guests.append(ctx.guest_name(g))
            cells.append({"day": d.isoformat(), "code": st.code,
                          "duty": "absent" if st.code in ctx.codes else "shift" if st.on_shift else "off",
                          "units": units, "guests": guests, "load": round(ctx.loads(d).get(e, 0.0), 2),
                          "warnings": sorted({w.kind for w in ctx.warnings(d) if w.employee_id == e})})
        rows.append({"employee_id": e, "name": ctx.name(e), "escort": e in ctx.escorts, "cells": cells})
    return {"days": [d.isoformat() for d in ctx.days()], "limit": ctx.limit, "rows": rows}


@dataclass(frozen=True)
class DayFilters:
    """Те же измерения фонда, что у шахматки (§7, views.fund_match) — по фонду ночи строки."""
    group_ids: tuple[int, ...] = ()
    category_ids: tuple[int, ...] = ()
    flag_ids: tuple[int, ...] = ()
    kind_ids: tuple[int, ...] = ()
    floor: str | None = None
    escorted_only: bool = False
    vip: bool = False
    employee_id: int | None = None
    q: str = ""


def _status(ctx: StaysContext, s: StayDay | None, night: dt.date, known, day: dt.date) -> dict:
    """Статус сопровождения брони в ночь night (§6.3): кто — кого / не назначено / подмена."""
    if s is None:
        return {"cover_status": "not_required"}
    if not s.escorted:
        return {"cover_status": "not_required"}
    if s.declined:
        return {"cover_status": "declined"}
    cover = ctx.cover(night)
    pairs: dict[int, list[str]] = {}
    for (rid, g), emps in cover.by_guest.items():
        if rid == s.reservation_id:
            for e in emps:
                pairs.setdefault(e, []).append(ctx.guest_name(g) if g != NO_GUESTS else "")
    covered = [{"employee_id": e, "name": ctx.name(e), "guests": [n for n in gs if n]} for e, gs in sorted(pairs.items())]
    replacement = [w for w in ctx.warnings(night) if w.kind == "need_replacement" and w.reservation_id == s.reservation_id]
    if s.reservation_id in cover.uncovered or replacement:
        return {"cover_status": "replacement" if replacement else "uncovered", "covered": covered,
                "candidates": _candidates(ctx, s, night, known) if night == day else []}
    return {"cover_status": "covered", "covered": covered}


def _candidates(ctx: StaysContext, s: StayDay, day: dt.date, known) -> list[dict]:
    return rank_in_ctx(ctx, day, [s], set(s.guests), known)[:3]


def _ooo_today(db: Session, ctx: StaysContext, day: dt.date, f: DayFilters) -> list[dict]:
    """OOO, которые начинаются или заканчиваются в этот день (часть 2 §6) — в «Требуют внимания».
    Причина — без персональных данных (решение владельца). Объект — по фильтрам фонда дня."""
    out = []
    for h in db.scalars(select(Ooo).where((Ooo.start == day) | (Ooo.end == day)).order_by(Ooo.start, Ooo.id)):
        if not fund_match(ctx.fund.on(day), h.unit_id, None, f):
            continue
        out.append({"kind": "ooo", "id": h.id, "unit_id": h.unit_id, "unit": ctx.unit_label(h.unit_id, day),
                    "title": h.reason, "start": h.start.isoformat(), "end": h.end.isoformat(),
                    "start_half": h.start_half, "end_half": h.end_half, "version": h.version,
                    "events": [e for e, d in (("starts", h.start), ("ends", h.end)) if d == day]})
    return out


def day_board(db: Session, day: dt.date, level: Level, f: DayFilters, duty: DutyPort) -> dict:
    prev = day - dt.timedelta(days=1)
    ctx = load_context(db, prev, day, duty)
    names = level != "occupancy"
    full = level == "full"
    stays_now = {s.reservation_id: s for s in ctx.stays_on(day)}
    stays_prev = {s.reservation_id: s for s in ctx.stays_on(prev)}
    no_show = [r for r in db.scalars(select(Reservation).where(Reservation.status == "no_show",
                                                                Reservation.check_in == day))
               if fund_match(ctx.fund.on(day), None, r.category_id, f)]
    rids = list(ctx.res)
    logistics: dict[int, list] = {}
    companions: dict[int, list] = {}
    if full and rids:
        for lg in db.scalars(select(Logistics).where(Logistics.reservation_id.in_(rids)).order_by(Logistics.time)):
            if lg.date in (None, day):
                logistics.setdefault(lg.reservation_id, []).append({"kind": lg.kind, "time": lg.time,
                                                                    "description": lg.description})
        for c in db.scalars(select(Companion).where(Companion.reservation_id.in_(rids))):
            companions.setdefault(c.reservation_id, []).append({"kind": c.kind, "description": c.description})
    all_guests = {g for s in stays_now.values() for g in s.guests if g != NO_GUESTS}
    known = _known(db, all_guests, day) if names and all_guests else {}
    needle = search_query(f.q) if names and f.q.strip() else ""
    # родственники среди проживающих в эту и прошлую ночь (§4: «мать — Петрова М.»)
    present = all_guests | {g for s in stays_prev.values() for g in s.guests if g != NO_GUESTS}
    relatives = {gid: [{"guest_id": o, "title": t, "name": ctx.guest_name(o)} for o, t in rel]
                 for gid, rel in kin_among(db, present).items()} if names else {}

    def guests_of(r: Reservation, night: dt.date) -> list[dict]:
        occ = sorted((o for o in ctx.occ.get(r.id, ()) if o.date_from <= night < o.date_to and o.guest_id in ctx.guests),
                     key=lambda o: (o.role != "main", o.id))
        return [{"guest_id": o.guest_id, "name": ctx.guest_name(o.guest_id), "level": ctx.guests[o.guest_id].level,
                 "role": o.role, **({"relatives": relatives.get(o.guest_id, [])} if names else {})} for o in occ]

    def row(r: Reservation, kind: str) -> dict | None:
        night = prev if kind == "departure" else day
        s = (stays_prev if kind == "departure" else stays_now).get(r.id)
        unit_id, piece = ctx.unit_of(r.id, night)          # тот же объект, что у s (StayDay)
        if not fund_match(ctx.fund.on(night), unit_id, piece.category_id if piece else r.category_id, f):
            return None
        guests = guests_of(r, night)
        base = {"reservation_id": r.id, "status": r.status, "unit": ctx.unit_label(unit_id, night),
                **({"overbooked": True} if unit_id is None else {}),
                "time": {"arrival": "РЗ" if r.early else "14:00", "departure": "ПВ" if r.late else "12:00"}.get(kind, ""),
                "guests_count": len(guests) or 1}
        if not names:
            return base
        st = _status(ctx, s, night, known, day)
        if f.escorted_only and st["cover_status"] == "not_required":
            return None
        if f.vip and not any(g["level"] != "regular" for g in guests):
            return None
        if f.employee_id and not any(c["employee_id"] == f.employee_id for c in st.get("covered", [])):
            return None
        if needle and needle not in (r.search_text or "") and not any(
                needle in (ctx.guests[g["guest_id"]].search_text or "") for g in guests) \
                and needle not in base["unit"].lower():
            return None
        out = {**base, **st, "number": r.number, "guests": guests}
        if full:
            prefs = [json.loads(ctx.guests[g["guest_id"]].preferences_json or "{}") for g in guests]
            out["details"] = {"logistics": logistics.get(r.id, []), "companions": companions.get(r.id, []),
                              "allergies": [p["allergy"] for p in prefs if p.get("allergy")]}
        return out

    def collect(rs, kind):
        return [x for r in rs if (x := row(r, kind)) is not None]

    res = sorted(ctx.res.values(), key=lambda r: (ctx.unit_label(ctx.unit_of(r.id, day)[0], day), r.id))
    arrivals = collect([r for r in res if r.check_in == day], "arrival")
    departures = collect([r for r in res if r.check_out == day], "departure")
    in_house = collect([r for r in res if r.id in stays_now], "in_house")
    out = {"date": day.isoformat(), "visibility": level, "arrivals": arrivals, "departures": departures,
           "in_house": in_house, "no_show": [{"reservation_id": r.id, "status": r.status, **(
               {"number": r.number} if names else {})} for r in no_show]}
    overbooked = [x for x in in_house if x.get("overbooked")]
    totals = {"arrivals": len(arrivals), "departures": len(departures), "in_house": len(in_house),
              "no_show": len(no_show), "overbooked": len(overbooked)}
    if names:
        statuses = [x["cover_status"] for x in in_house]
        guests = [g["level"] for x in in_house for g in x["guests"]]
        totals |= {"covered": statuses.count("covered"), "uncovered": statuses.count("uncovered"),
                   "need_replacement": statuses.count("replacement"), "declined": statuses.count("declined"),
                   "not_required": statuses.count("not_required"), "vip": guests.count("vip"),
                   "vvip": guests.count("vvip")}
    # «Требуют внимания» — всем уровням (решение владельца: OOO видны всем): овербукинг (бронь без
    # объекта, часть 2 §4.2) и OOO дня; на уровне «занятость» строки броней — без данных гостей,
    # непокрытые и подмены — только с уровня «имена»
    out["attention"] = [x for x in in_house if x.get("overbooked") or (
        names and x["cover_status"] in ("uncovered", "replacement"))] + _ooo_today(db, ctx, day, f)
    out["totals"] = totals
    return out
