"""История (§3.6): лента изменений брони — из общего журнала аудита; история проживаний
гостя — по записям «проживающий» во всех его бронях."""
from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import manifest
from app.core.audit import AuditLog
from app.modules.employees.application.catalog import Employee

from ..adapters.orm import Assignment, CoverageGuest, CoverageLine, Guest, Occupant, Reservation
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


def guest_stays(db: Session, gid: int) -> list[dict]:
    """Где, когда и в какой роли жил гость и кто его вёл."""
    occ = list(db.scalars(select(Occupant).where(Occupant.guest_id == gid)))
    rids = {o.reservation_id for o in occ}
    if not rids:
        return []
    res = {r.id: r for r in db.scalars(select(Reservation).where(Reservation.id.in_(rids)))}
    unit_ids: dict[int, list[int]] = {rid: [] for rid in rids}
    # seg_index — индекс части (сегмент * PIECE_BASE + n): порядок частей — порядок во времени
    for a in db.scalars(select(Assignment).where(Assignment.reservation_id.in_(rids)).order_by(Assignment.seg_index)):
        if a.unit_id and a.unit_id not in unit_ids[a.reservation_id]:
            unit_ids[a.reservation_id].append(a.unit_id)
    # обозначения — на дату записи «проживающий» (фонд меняется версиями с даты)
    fund = fund_for_stays(db, min(o.date_from for o in occ), max(o.date_to for o in occ))

    def units_of(o: Occupant) -> list[str]:
        return list(dict.fromkeys(u.label for uid in unit_ids[o.reservation_id]
                                  if (u := fund.unit(uid, o.date_from)) is not None))
    butlers = _butlers_of(db, gid, occ, res)
    out = [{"reservation_id": o.reservation_id, "number": res[o.reservation_id].number,
            "status": res[o.reservation_id].status, "status_title": STATUS_TITLES[res[o.reservation_id].status],
            "units": units_of(o), "date_from": o.date_from.isoformat(),
            "date_to": o.date_to.isoformat(), "role": o.role, "butlers": butlers.get(o.id, [])} for o in occ]
    return sorted(out, key=lambda s: (s["date_from"], s["reservation_id"]), reverse=True)


def _butlers_of(db: Session, gid: int, occ: list[Occupant], res: dict[int, Reservation]) -> dict[int, list[str]]:
    """Проживающий → батлеры, которые вели этого гостя в его даты (вся бронь, группа или он сам)."""
    groups = {r.group_id for r in res.values() if r.group_id is not None}
    q = select(CoverageLine)
    rows = list(db.scalars(q.where(CoverageLine.reservation_id.in_(list(res))))) + (
        list(db.scalars(q.where(CoverageLine.group_id.in_(groups)))) if groups else [])
    if not rows:
        return {}
    picked: dict[int, set[int]] = {r.id: set() for r in rows}
    for cg in db.scalars(select(CoverageGuest).where(CoverageGuest.coverage_id.in_(list(picked)))):
        picked[cg.coverage_id].add(cg.guest_id)
    names = dict(db.execute(select(Employee.id, Employee.full_name).where(
        Employee.id.in_({r.employee_id for r in rows}))).all())
    out: dict[int, list[str]] = {}
    for o in occ:
        r = res[o.reservation_id]
        for ln in rows:
            hit = (ln.reservation_id == r.id or (ln.group_id is not None and ln.group_id == r.group_id)) \
                and o.date_from <= ln.day < o.date_to and (not picked[ln.id] or gid in picked[ln.id])
            if hit and names.get(ln.employee_id) not in out.setdefault(o.id, []):
                out[o.id].append(names.get(ln.employee_id, ""))
    return out
