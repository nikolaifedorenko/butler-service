"""Брони: документ, статусы с no-show, группы совместного проживания (§3.3, §4.7, §9).

Каждая операция пересчитывает распределение по объектам и пишет журнал «было → стало»;
устаревшая версия брони — 409. Предпросмотр — тот же код с откатом (``run_previewed``).
Батлер (часть 4 §4) правит только свою бронь и только разрешённые поля.
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy.orm import Session

from app.core.audit import audit
from app.core.auth import Principal
from app.core.db import transactional
from app.core.errors import NotFound, Validation

from ..adapters.orm import Reservation, StayGroup
from ..ports.duty import DutyPort
from . import allocation, coverage, mine, reservations
from .guest_access import butler_id
from .previewed import run_previewed
from .reservation_forms import GroupIn, JoinIn, LeaveIn, ReservationIn, StatusIn


def mine_mode(db: Session, principal: Principal, rid: int) -> bool:
    """Без ``stays.edit`` — батлер: только своя бронь (строка покрытия за всё время, часть 4 §4)."""
    if "stays.edit" in principal.gate_permissions:
        return False
    if principal.employee is None or not mine.owns_reservation(db, principal.employee.id, rid):
        raise mine.MineForbidden("Это не ваша бронь: вы не ведёте её гостей")
    return True


def _doc(payload: ReservationIn) -> dict:
    return payload.model_dump(exclude={"version"})


def _result(db: Session, r: Reservation) -> dict:
    return reservations.reservation_dict(db, r, allocation.current_state(db))


def _window(r: Reservation | None, *docs) -> tuple[dt.date, dt.date]:
    """Дни, на которые операция может повлиять: старые и новые даты брони."""
    starts = [d["check_in"] for d in docs] + ([r.check_in] if r else [])
    ends = [d["check_out"] for d in docs] + ([r.check_out] if r else [])
    return min(starts), max(max(ends) - dt.timedelta(days=1), min(starts))


def _span(rs: list[Reservation]) -> tuple[dt.date, dt.date]:
    return _window(None, *({"check_in": r.check_in, "check_out": r.check_out} for r in rs))


def _cleanup(db: Session, principal: Principal, r: Reservation, old_group_id: int | None = None) -> None:
    """Строки покрытия на дни, когда гостей брони уже нет, снимаются с записью в журнал (§4.2)."""
    removed = coverage.cleanup_lines(db, r.id, old_group_id)
    if removed:
        audit(db, principal, "stays_coverage_cleanup", f"reservation:{r.id}", {"days": removed})


def _may_overbook(principal: Principal) -> bool:
    return "stays.overbook" in principal.gate_permissions


def get(db: Session, principal: Principal, rid: int) -> dict:
    r = db.get(Reservation, rid)
    if r is None:
        raise NotFound("Бронь не найдена")
    mine_mode(db, principal, rid)
    return reservations.reservation_dict(db, r)


def create(db: Session, principal: Principal, payload: ReservationIn, *, preview_only: bool,
           duty: DutyPort | None = None) -> dict:
    doc = _doc(payload)

    def operation():
        r, before = reservations.save_reservation(db, doc, None, None)
        audit(db, principal, "stays_reservation", f"reservation:{r.id}",
              {"diff": reservations.diff_of(before, db, r)})
        return _result(db, r)
    return run_previewed(db, operation, preview_only=preview_only, may_overbook=_may_overbook(principal),
                         window=_window(None, doc), duty=duty)


def update(db: Session, principal: Principal, rid: int, payload: ReservationIn, *, preview_only: bool,
           duty: DutyPort | None = None) -> dict:
    if payload.version is None:
        raise Validation("Не указана версия брони")
    doc = _doc(payload)
    r0 = db.get(Reservation, rid)
    butler: int | None = None             # батлер правит свою бронь (часть 4 §4)
    had: set[int] = set()
    if r0 is not None and mine_mode(db, principal, rid):
        butler = butler_id(principal)
        current = reservations.reservation_dict(db, r0, with_escort=False)
        had = {o["guest_id"] for o in current["occupants"]}
        mine.check_reservation_change(db, current, doc)
    window = _window(r0, doc)
    old_group = r0.group_id if r0 else None

    def operation():
        owned_before = mine.owned_among(db, butler, had) if butler is not None else set()
        r, before = reservations.save_reservation(db, doc, rid, payload.version)
        audit(db, principal, "stays_reservation", f"reservation:{r.id}",
              {"diff": reservations.diff_of(before, db, r)})
        _cleanup(db, principal, r, old_group)
        if butler is not None:
            mine.check_no_gained_guests(db, butler, had, owned_before)       # решение 9 — 403
        return _result(db, r)
    return run_previewed(db, operation, preview_only=preview_only, may_overbook=_may_overbook(principal),
                         window=window, duty=duty)


def change_status(db: Session, principal: Principal, rid: int, payload: StatusIn, *, preview_only: bool,
                  duty: DutyPort | None = None) -> dict:
    r0 = db.get(Reservation, rid)
    window = _window(r0) if r0 else None

    def operation():
        r, before = reservations.set_status(db, rid, payload.status, payload.version, payload.new_check_in)
        audit(db, principal, "stays_reservation_status", f"reservation:{r.id}",
              {"diff": reservations.diff_of(before, db, r)})
        _cleanup(db, principal, r)
        return _result(db, r)
    return run_previewed(db, operation, preview_only=preview_only, may_overbook=_may_overbook(principal),
                         window=window, duty=duty)


def cohabit(db: Session, rid: int) -> list[dict]:
    """С кем бронь может жить вместе (кандидаты на группу совместного проживания)."""
    try:
        return reservations.cohabit_candidates(db, rid)
    except reservations.ReservationInvalid as e:
        raise NotFound(str(e)) from e


def join_group(db: Session, principal: Principal, payload: JoinIn, *, preview_only: bool,
               duty: DutyPort | None = None) -> dict:
    """Совместное проживание (§3.3): брони — в одну группу, с предпросмотром размещения."""
    found = [r for r in (db.get(Reservation, i) for i in payload.reservation_ids) if r is not None]

    def operation():
        gid, saved = reservations.join_group(db, payload.reservation_ids)
        for r, before in saved:
            audit(db, principal, "stays_reservation", f"reservation:{r.id}",
                  {"diff": reservations.diff_of(before, db, r)})
        return {"group_id": gid}
    return run_previewed(db, operation, preview_only=preview_only, may_overbook=_may_overbook(principal),
                         window=_span(found) if found else None, duty=duty)


def leave_group(db: Session, principal: Principal, payload: LeaveIn, *, preview_only: bool,
                duty: DutyPort | None = None) -> dict:
    r0 = db.get(Reservation, payload.reservation_id)

    def operation():
        r, before, old = reservations.leave_group(db, payload.reservation_id)
        audit(db, principal, "stays_reservation", f"reservation:{r.id}",
              {"diff": reservations.diff_of(before, db, r)})
        _cleanup(db, principal, r, old)
        return _result(db, r)
    return run_previewed(db, operation, preview_only=preview_only, may_overbook=_may_overbook(principal),
                         window=_span([r0]) if r0 else None, duty=duty)


@transactional
def create_group(db: Session, principal: Principal, payload: GroupIn) -> dict:
    g = StayGroup(title=payload.title)
    db.add(g)
    db.flush()
    audit(db, principal, "stays_reservation", f"group:{g.id}", {"title": payload.title})
    return {"id": g.id, "title": g.title}
