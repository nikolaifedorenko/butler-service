"""Запись профилей гостей: профиль, связи, пожелания, объединение дублей (§3.2, §8).

Запись профиля — ``stays.edit``; батлер (часть 4 §3) правит только своих гостей и только
разрешённые поля. Операции с предпросмотром (смена кода, пожелания, объединение) идут через
``run_previewed``: предпросмотр откатывается, сохранение фиксируется.
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy.orm import Session

from app.core.audit import audit
from app.core.auth import Principal
from app.core.db import transactional
from app.core.errors import Forbidden, NotFound
from app.core.time import local_date

from ..adapters.orm import Guest
from ..ports.duty import DutyPort
from . import allocation, guests, mine, reservations
from .guest_access import own_guest, own_link, require_full
from .guest_forms import FormerIn, GuestIn, GuestUpdateIn, LinkIn, MergeIn, PrefsIn
from .guest_screen import card
from .previewed import run_previewed


def _data(data: dict) -> dict:
    return {**data, "special_dates": [{"date": d["date"].isoformat(), "what": d["what"]} for d in data["special_dates"]]}


@transactional
def create(db: Session, principal: Principal, payload: GuestIn) -> dict:
    g, before = guests.save_guest(db, _data(payload.model_dump()), None)
    audit(db, principal, "stays_guest", f"guest:{g.id}", {"diff": guests.guest_changes(before, g)})
    return card(db, g)


def update(db: Session, principal: Principal, gid: int, payload: GuestUpdateIn, *, preview_only: bool,
           duty: DutyPort | None = None) -> dict:
    """Правка профиля. Код сменился и ``update_reservations`` — той же операцией код переходит в
    текущие и будущие брони, где гость главный; предпросмотр показывает, что изменится (окно — от
    сегодня до самого позднего выезда этих броней). ``diff`` — только если код менялся."""
    data = payload.model_dump(exclude={"update_reservations"})
    g = db.get(Guest, gid)
    window = None
    if g is not None:
        if own_guest(db, principal, gid, "stays.edit"):
            mine.check_guest_change(guests.guest_dict(g), data)
        if payload.update_reservations and payload.vip_code_id != g.vip_code_id:
            today = local_date()
            ahead = reservations.main_reservations(db, gid, today)
            if ahead:
                window = (today, max(r.check_out for r in ahead) - dt.timedelta(days=1))

    def operation() -> dict:
        saved, before = guests.save_guest(db, _data(data), gid)
        audit(db, principal, "stays_guest", f"guest:{saved.id}", {"diff": guests.guest_changes(before, saved)})
        done = 0
        if payload.update_reservations and saved.vip_code_id != before.get("vip_code_id"):
            # под замком модуля: состав броней перечитан после записи профиля
            affected = reservations.main_reservations(db, gid, local_date())
            for r, was in reservations.set_main_code(db, affected, saved.vip_code_id):
                audit(db, principal, "stays_reservation", f"reservation:{r.id}",
                      {"diff": {"vip_code_id": [was, r.vip_code_id]}})
                done += 1
        return {"guest": card(db, saved), "updated_reservations": done}

    out = run_previewed(db, operation, preview_only=preview_only,
                        may_overbook="stays.overbook" in principal.gate_permissions,
                        window=window, duty=duty)
    return {"preview": out["preview"], **out["result"], "diff": out["diff"] if window else None,
            "overbook_refused": out["overbook_refused"]}


def set_prefs(db: Session, principal: Principal, gid: int, payload: PrefsIn, *, preview_only: bool) -> dict:
    """Заменить пожелания гостя целиком. Распределение пересчитывается тут же (брони гостя могут
    переехать): предпросмотр показывает, кто переедет; новый овербукинг без права
    ``stays.overbook`` — 409. ``stays.edit`` — с полным уровнем; батлер — своему гостю."""
    if db.get(Guest, gid) is None:
        raise NotFound("Гость не найден")
    if not own_guest(db, principal, gid, "stays.edit"):
        require_full(db, principal)

    def operation() -> list[dict]:
        before = guests.prefs_of(db, gid)               # под замком модуля (run_operation)
        after = guests.save_prefs(db, gid, [p.model_dump() for p in payload.prefs])
        allocation.run_allocation(db)
        audit(db, principal, "stays_guest_prefs", f"guest:{gid}", {"diff": {"prefs": [before, after]}})
        return after

    return run_previewed(db, operation, preview_only=preview_only,
                         may_overbook="stays.overbook" in principal.gate_permissions)


def merge(db: Session, principal: Principal, payload: MergeIn, *, preview_only: bool) -> dict:
    """Объединение дублей: предпросмотр — что перенесётся, тем же кодом с откатом."""
    require_full(db, principal)

    def operation() -> dict:
        out = guests.merge_guests(db, payload.keep_id, payload.drop_id)
        audit(db, principal, "stays_guest_merge", f"guest:{payload.keep_id}",
              {"drop_id": payload.drop_id, "not_carried": out.pop("not_carried"), "moves": out["moves"]})
        return out

    done = run_previewed(db, operation, preview_only=preview_only,
                         may_overbook="stays.overbook" in principal.gate_permissions)
    return {"preview": done["preview"], **done["result"], "diff": done["diff"],
            "overbook_refused": done["overbook_refused"]}


@transactional
def add_link(db: Session, principal: Principal, gid: int, payload: LinkIn) -> dict:
    """Связь, при необходимости — с новым гостем и вторым родителем: всё одной записью под
    замком модуля; отказ любой проверки — 422, не создаётся ничего. Батлер — только своему гостю;
    заведённый им новый человек становится его «своим» (часть 4 §3)."""
    butler = own_guest(db, principal, gid, "stays.edit")
    if butler:
        # существующая вторая сторона и второй родитель — тоже свои: иначе связью «прямая связь»
        # батлер открыл бы себе чужой профиль (через состав брони); новый человек — свободно
        for other_id in (payload.guest_id, payload.also_parent_id):
            if other_id is not None and not mine.owns_guest(db, principal.employee.id, other_id):
                raise Forbidden("Связать можно только со своим гостем или новым человеком")
    rows, other = guests.add_links(
        db, gid, payload.kind, other_id=payload.guest_id,
        new_guest=payload.new_guest.model_dump() if payload.new_guest else None, former=payload.former,
        other_is_parent=payload.other_is_parent, also_parent_id=payload.also_parent_id,
        created_by=principal.employee.id if butler else None)    # заведённый батлером — его «свой»
    if payload.new_guest:
        audit(db, principal, "stays_guest", f"guest:{other}", {"created": payload.new_guest.model_dump()})
    for row in rows:
        audit(db, principal, "stays_guest_link", f"guest:{row.guest_a_id}",
              {"added": {"guest_id": row.guest_b_id, "kind": row.kind, "former": row.former, "link_id": row.id}})
    return {"id": rows[0].id, "guest_id": other, "ids": [r.id for r in rows]}


@transactional
def set_link_former(db: Session, principal: Principal, link_id: int, payload: FormerIn) -> dict:
    """«Бывшие» на линии супругов в редакторе дерева: снять — только если у обоих нет другого
    действующего супруга (422). Батлер — если хотя бы одна сторона своя."""
    own_link(db, principal, link_id)
    row, before = guests.set_former(db, link_id, payload.former)
    audit(db, principal, "stays_guest_link", f"guest:{row.guest_a_id}",
          {"former": [before, row.former], "guest_id": row.guest_b_id, "link_id": link_id})
    return {"id": row.id, "former": row.former}


@transactional
def remove_link(db: Session, principal: Principal, link_id: int) -> dict:
    """Батлер — если хотя бы одна сторона связи своя."""
    own_link(db, principal, link_id)
    row = guests.delete_link(db, link_id)
    audit(db, principal, "stays_guest_link", f"guest:{row.guest_a_id}",
          {"removed": {"guest_id": row.guest_b_id, "kind": row.kind, "link_id": link_id}})
    return {"ok": True}
