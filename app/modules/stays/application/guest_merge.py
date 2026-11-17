"""Объединение дублей гостей (addendum §3): профиль, связи и пожелания сливает ``guests``, а то, что
лежит в бронях — проживания и строки покрытия — и пересчёт размещения делают брони.

Предпросмотр — этот же код с откатом (``previewed.run_previewed``). Ничего не коммитит.
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app.modules.fund.application.locking import lock_module
from app.modules.guests.application import guests
from app.modules.guests.application.catalog import Guest

from ..adapters.orm import CoverageGuest, Occupant, Reservation
from . import allocation


def _nights_runs(rows: list[Occupant]) -> list[tuple[dt.date, dt.date, str]]:
    """Проживание одного человека в брони по ночам: главный, если хоть одна запись главная
    в эту ночь; подряд идущие ночи с одной ролью — одна запись."""
    roles: dict[dt.date, str] = {}
    for o in rows:
        d = o.date_from
        while d < o.date_to:
            roles[d] = "main" if o.role == "main" or roles.get(d) == "main" else "guest"
            d += dt.timedelta(days=1)
    runs: list[list] = []
    for d in sorted(roles):
        if runs and runs[-1][1] == d and runs[-1][2] == roles[d]:
            runs[-1][1] = d + dt.timedelta(days=1)
        else:
            runs.append([d, d + dt.timedelta(days=1), roles[d]])
    return [tuple(r) for r in runs]


def merge_occupants(db: Session, keep_id: int, drop_id: int) -> list[dict]:
    """Записи «проживающий» дубля → оставляемому. Если оба живут в одной брони (Review Focus 1),
    их записи сливаются в записи одного человека: без дубля в составе, главный — там, где
    главным был любой из двух (двух главных на ночь у брони не бывает)."""
    drop_occ = list(db.scalars(select(Occupant).where(Occupant.guest_id == drop_id).order_by(Occupant.id)))
    rids = sorted({o.reservation_id for o in drop_occ})
    if not rids:
        return []
    keep_occ = list(db.scalars(select(Occupant).where(Occupant.guest_id == keep_id,
                                                      Occupant.reservation_id.in_(rids)).order_by(Occupant.id)))
    shared = {o.reservation_id for o in keep_occ}
    for o in drop_occ:
        if o.reservation_id not in shared:
            o.guest_id = keep_id
    for rid in sorted(shared):
        rows = [o for o in keep_occ + drop_occ if o.reservation_id == rid]
        runs = _nights_runs(rows)
        for o in rows:
            db.delete(o)
        db.add_all(Occupant(reservation_id=rid, guest_id=keep_id, date_from=a, date_to=b, role=role)
                   for a, b, role in runs)
    out = []
    for r in db.scalars(select(Reservation).where(Reservation.id.in_(rids)).order_by(Reservation.id)):
        r.version += 1                       # открытая форма брони со старым составом получит 409
        out.append({"id": r.id, "number": r.number, "shared": r.id in shared})
    db.flush()
    return out


def merge_coverage(db: Session, keep_id: int, drop_id: int) -> int:
    """Строки покрытия, где дубль выбран явно, — на оставляемого (без повтора в строке)."""
    lines = set(db.scalars(select(CoverageGuest.coverage_id).where(CoverageGuest.guest_id == drop_id)))
    if not lines:
        return 0
    both = set(db.scalars(select(CoverageGuest.coverage_id).where(CoverageGuest.guest_id == keep_id,
                                                                  CoverageGuest.coverage_id.in_(lines))))
    if both:
        db.execute(delete(CoverageGuest).where(CoverageGuest.guest_id == drop_id,
                                               CoverageGuest.coverage_id.in_(both)))
    db.execute(update(CoverageGuest).where(CoverageGuest.guest_id == drop_id).values(guest_id=keep_id))
    return len(lines)


def merge_guests(db: Session, keep_id: int, drop_id: int) -> dict:
    """Объединить дубль drop в keep (addendum §3): проживания, строки покрытия, связи,
    предпочтения, особые даты, настраиваемые поля переходят к keep, профиль drop удаляется.
    Ввод — 422, нарушение семейного дерева — 409; все проверки — до первой записи.
    Предпросмотр — этот же код с откатом (preview.run_operation). Ничего не коммитит."""
    lock_module(db)
    if keep_id == drop_id:
        raise guests.GuestError("Нельзя объединить гостя с самим собой")
    keep, drop = db.get(Guest, keep_id), db.get(Guest, drop_id)
    if keep is None or drop is None:
        raise guests.GuestError("Гость не найден")
    plan = guests.plan_links(db, keep_id, drop_id)
    dropped = guests.guest_dict(drop)
    moved = merge_occupants(db, keep_id, drop_id)
    covered = merge_coverage(db, keep_id, drop_id)
    links = guests.apply_links(db, plan, keep_id)
    prefs = guests.merge_prefs(db, keep_id, drop_id)
    merged = guests.merge_profile(db, keep, drop)
    if keep.created_by_employee_id != drop.created_by_employee_id:
        # автор профиля делает гостя «своим» батлеру (часть 4 §3): у слитого профиля — история
        # обоих, автор остаётся, только если он у обоих один (решение 10)
        keep.created_by_employee_id = None
    db.delete(drop)
    db.flush()
    keep.search_text = guests.guest_search_text(keep, guests.searchable_codes(db, "guest"))
    db.flush()
    allocation.run_allocation(db)               # пожелания keep теперь действуют на перенесённые брони
    return {"keep_id": keep_id, "drop_id": drop_id, "not_carried": guests.not_carried(dropped, guests.guest_dict(keep)),
            "moves": {"reservations": moved, "links": links, "coverage": covered, "prefs": prefs, **merged}}
