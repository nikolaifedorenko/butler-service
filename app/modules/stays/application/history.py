"""История (§3.6): лента изменений брони — из общего журнала аудита; история проживаний
гостя — по записям «проживающий» во всех его бронях."""
from __future__ import annotations

import datetime as dt
import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import manifest
from app.core.audit import AuditLog
from app.modules.people.application.catalog import Employee

from ..adapters.orm import Assignment, CoverageGuest, CoverageLine, Guest, Occupant, Reservation
from . import allocation
from .fund_versions import fund_for_stays
from .guests import short_name
from .reservations import STATUS_TITLES
from .visibility import Level

# поля журнала, которые видит уровень «с фамилиями» (§8); остальное — только полному
NAMES_DIFF = {"number", "check_in", "check_out", "early", "late", "category_id", "label_id", "group_id",
              "status", "moves", "units", "occupants"}


def _named_occupants(rows, names: dict[int, str]):
    return [[names.get(o[0], "?"), *o[1:]] for o in rows or []]


def reservation_history(db: Session, rid: int, level: Level) -> list[dict]:
    """Лента «было → стало»; состав — короткими именами, поля полного уровня — только ему."""
    titles = manifest.audit_titles()
    rows = list(db.scalars(select(AuditLog).where(AuditLog.target == f"reservation:{rid}")
                           .order_by(AuditLog.id.desc())))
    diffs = [json.loads(a.payload_json or "{}").get("diff", {}) for a in rows]
    gids = {o[0] for d in diffs for side in d.get("occupants", ()) for o in side or ()}
    names = {g.id: short_name(g) for g in db.scalars(select(Guest).where(Guest.id.in_(gids)))} if gids else {}
    out = []
    for a, d in zip(rows, diffs, strict=True):
        if level != "full":
            d = {k: v for k, v in d.items() if k in NAMES_DIFF}
        if "occupants" in d:
            d = {**d, "occupants": [_named_occupants(side, names) for side in d["occupants"]]}
        out.append({"ts": a.ts.isoformat(), "actor": a.actor_name, "action": a.action,
                    "title": titles.get(a.action, a.action), "diff": d})
    return out


def _stay_units(db: Session, occ: list[Occupant], rids: set[int]):
    """Объекты, где жил гость по записи «проживающий»: в порядке частей, обозначения — по фонду на
    дату записи (фонд меняется версиями с даты)."""
    unit_ids: dict[int, list[int]] = {rid: [] for rid in rids}
    # seg_index — индекс части (сегмент * PIECE_BASE + n): порядок частей — порядок во времени
    for a in db.scalars(select(Assignment).where(Assignment.reservation_id.in_(rids)).order_by(Assignment.seg_index)):
        if a.unit_id and a.unit_id not in unit_ids[a.reservation_id]:
            unit_ids[a.reservation_id].append(a.unit_id)
    fund = fund_for_stays(db, min(o.date_from for o in occ), max(o.date_to for o in occ))

    def units_of(o: Occupant) -> list[str]:
        return list(dict.fromkeys(u.label for uid in unit_ids[o.reservation_id]
                                  if (u := fund.unit(uid, o.date_from)) is not None))
    return units_of


def guest_stays(db: Session, gid: int) -> list[dict]:
    """Где, когда и в какой роли жил гость и кто его вёл."""
    occ = list(db.scalars(select(Occupant).where(Occupant.guest_id == gid)))
    rids = {o.reservation_id for o in occ}
    if not rids:
        return []
    res = {r.id: r for r in db.scalars(select(Reservation).where(Reservation.id.in_(rids)))}
    units_of = _stay_units(db, occ, rids)
    led, staff = _led_nights(db, gid, occ, res)
    butlers = {oid: list(dict.fromkeys(staff[e].full_name if e in staff else "" for e in by_emp))
               for oid, by_emp in led.items()}
    out = [{"reservation_id": o.reservation_id, "number": res[o.reservation_id].number,
            "status": res[o.reservation_id].status, "status_title": STATUS_TITLES[res[o.reservation_id].status],
            "units": units_of(o), "date_from": o.date_from.isoformat(),
            "date_to": o.date_to.isoformat(), "role": o.role, "butlers": butlers.get(o.id, [])} for o in occ]
    return sorted(out, key=lambda s: (s["date_from"], s["reservation_id"]), reverse=True)


def guest_led_history(db: Session, gid: int, employee_id: int) -> list[dict]:
    """История проживаний гостя для батлера (часть 4 §5): брони, где гость жил (без отменённых и
    «не заехал»), объекты, и кто его вёл — непрерывными отрезками ночей: first — первая ночь,
    last — утро после последней («вёл я 03.05–08.05» при выезде 08.05); me — это сам батлер."""
    occ = list(db.scalars(select(Occupant).where(Occupant.guest_id == gid)))
    rids = {o.reservation_id for o in occ}
    res = {r.id: r for r in db.scalars(select(Reservation).where(
        Reservation.id.in_(rids), Reservation.status.in_(allocation.OCCUPYING)))} if rids else {}
    occ = [o for o in occ if o.reservation_id in res]
    if not occ:
        return []
    units_of = _stay_units(db, occ, set(res))
    led, staff = _led_nights(db, gid, occ, res)
    names = {e.id: e.short_name or e.full_name for e in staff.values()}
    stays: dict[int, dict] = {}
    nights: dict[int, dict[int, set[dt.date]]] = {}
    for o in sorted(occ, key=lambda o: o.date_from):
        s = stays.setdefault(o.reservation_id, {"reservation_id": o.reservation_id, "number": res[o.reservation_id].number,
                                                "status": res[o.reservation_id].status, "check_in": o.date_from,
                                                "check_out": o.date_to, "units": []})
        s["check_in"], s["check_out"] = min(s["check_in"], o.date_from), max(s["check_out"], o.date_to)
        s["units"] += [u for u in units_of(o) if u not in s["units"]]
        for e, days in led.get(o.id, {}).items():
            nights.setdefault(o.reservation_id, {}).setdefault(e, set()).update(days)
    out = []
    for rid, s in stays.items():
        runs = [{"employee_id": e, "name": names.get(e, ""), "me": e == employee_id, "first": a.isoformat(),
                 "last": (z + dt.timedelta(days=1)).isoformat()}
                for e, days in nights.get(rid, {}).items() for a, z in _runs(days)]
        out.append({"reservation_id": rid, "number": s["number"], "status": s["status"],
                    "check_in": s["check_in"].isoformat(), "check_out": s["check_out"].isoformat(),
                    "unit": " → ".join(s["units"]) or "без объекта",
                    "led": sorted(runs, key=lambda x: (x["first"], x["name"]))})
    return sorted(out, key=lambda s: (s["check_in"], s["reservation_id"]), reverse=True)


def _runs(days: set[dt.date]) -> list[tuple[dt.date, dt.date]]:
    """Ночи → непрерывные отрезки [(первая, последняя)]."""
    out: list[tuple[dt.date, dt.date]] = []
    for d in sorted(days):
        if out and d == out[-1][1] + dt.timedelta(days=1):
            out[-1] = (out[-1][0], d)
        else:
            out.append((d, d))
    return out


def _led_nights(db: Session, gid: int, occ: list[Occupant],
                res: dict[int, Reservation]) -> tuple[dict[int, dict[int, set[dt.date]]], dict[int, Employee]]:
    """Проживающий → {батлер → ночи, когда он вёл этого гостя} и сотрудники-батлеры. Строка «вся бронь /
    группа» ведёт гостя, если в ту ночь его явно не ведёт другая строка брони или её группы
    (явный список сильнее, domain/coverage.resolve_day). Запросов — постоянное число."""
    groups = {r.group_id for r in res.values() if r.group_id is not None}
    q = select(CoverageLine)
    rows = list(db.scalars(q.where(CoverageLine.reservation_id.in_(list(res))))) + (
        list(db.scalars(q.where(CoverageLine.group_id.in_(groups)))) if groups else [])
    if not rows:
        return {}, {}
    picked: dict[int, set[int]] = {r.id: set() for r in rows}
    for cg in db.scalars(select(CoverageGuest).where(CoverageGuest.coverage_id.in_(list(picked)))):
        picked[cg.coverage_id].add(cg.guest_id)
    staff = {e.id: e for e in db.scalars(select(Employee).where(Employee.id.in_({r.employee_id for r in rows})))}
    out: dict[int, dict[int, set[dt.date]]] = {}
    for o in occ:
        r = res[o.reservation_id]
        mine = [ln for ln in rows if (ln.reservation_id == r.id or (ln.group_id is not None and ln.group_id == r.group_id))
                and o.date_from <= ln.day < o.date_to]
        explicit = {ln.day for ln in mine if gid in picked[ln.id]}
        for ln in mine:
            if gid in picked[ln.id] or (not picked[ln.id] and ln.day not in explicit):
                out.setdefault(o.id, {}).setdefault(ln.employee_id, set()).add(ln.day)
    return out, staff
