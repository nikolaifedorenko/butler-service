"""Шахматка объектов, карточки брони и гостя, лента изменений (§6, §8).

Уровень видимости персональных данных определяется правами (§8); у батлера (часть 4 §6) своя
бронь открывается целиком. Роутер проверяет право эндпоинта.
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy.orm import Session

from app.core.auth import Principal
from app.core.errors import NotFound
from app.modules.guests.application import guests
from app.modules.guests.application.catalog import Guest
from app.modules.stays.application import history, reservations
from app.modules.stays.application.guest_access import my_reservations, own_guest
from app.modules.stays.application.visibility import Level, required_level
from app.modules.stays.ports.duty import DutyPort

from . import views


def units_board(db: Session, principal: Principal, first: dt.date, last: dt.date, f: views.BoardFilters) -> dict:
    """Шахматка объектов: полосы броней, блоки, OOO; поля — по уровню видимости."""
    return views.units_board(db, first, last, f, required_level(db, principal), my_reservations(db, principal))


def _level_for_reservation(db: Session, principal: Principal, rid: int,
                           mine_ids: set[int] | None) -> Level:
    """Своя бронь батлера — целиком (часть 4 §6), даже без общего уровня; иначе уровень по правам."""
    if mine_ids is not None and rid in mine_ids:
        return "full"
    return required_level(db, principal)


def reservation_card(db: Session, principal: Principal, rid: int, duty: DutyPort) -> dict:
    mine_ids = my_reservations(db, principal)
    level = _level_for_reservation(db, principal, rid, mine_ids)
    try:
        card = views.reservation_card(db, rid, level, duty)
    except LookupError as e:
        raise NotFound(str(e)) from e
    # батлеру — «Изменить» и «Карточка» своей брони; остальным признака нет
    card["mine"] = None if mine_ids is None else rid in mine_ids
    for key in ("customer", "note", "fields", "companions", "logistics"):   # только полный уровень
        card.setdefault(key, None)
    return card


def reservation_history(db: Session, principal: Principal, rid: int) -> list[dict]:
    mine_ids = my_reservations(db, principal)
    return history.reservation_history(db, rid, _level_for_reservation(db, principal, rid, mine_ids))


def guest_card(db: Session, principal: Principal, gid: int) -> dict:
    """Карточка гостя целиком (с историей проживаний): ``stays.guests`` — любого, ``stays.mine`` — своего."""
    g = db.get(Guest, gid)
    if g is None:
        raise NotFound("Гость не найден")
    own_guest(db, principal, gid, "stays.guests")
    return {**guests.guest_dict(g), **reservations.guest_profile_extra(db, g), "links": guests.links_of(db, gid),
            "stays": history.guest_stays(db, gid)}
