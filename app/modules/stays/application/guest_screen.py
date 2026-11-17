"""Чтение профилей гостей: подбор, вкладка «Гости», карточка, история, пожелания, семья (§3.2, §4, §8).

Список с фамилиями — ``stays.view``, карточка целиком — ``stays.guests``; батлер (часть 4 §3) —
только свои гости. Роутер проверяет право эндпоинта, остальные проверки — здесь.
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy.orm import Session

from app.core.auth import Principal
from app.core.errors import Forbidden, NotFound
from app.modules.guests.application import family as family_graph
from app.modules.guests.application import guests, vip_codes
from app.modules.guests.application.catalog import Guest

from . import guests_list, history, mine
from .guest_access import own_guest, require_full
from .guest_card import card
from .visibility import at_least, level_for


def _guest(db: Session, gid: int) -> Guest:
    g = db.get(Guest, gid)
    if g is None:
        raise NotFound("Гость не найден")
    return g


def search(db: Session, principal: Principal, q: str, mine_only: bool) -> list[dict]:
    """Подбор гостя: без контактов и дат рождения. Полный уровень — по ФИО, телефону, почте и
    полям с поиском; ниже — только по ФИО (решение 8: иначе по ответу подбирается чужой телефон).
    ``mine_only`` — только свои гости батлера (редактор связей, часть 4 §3)."""
    full = level_for(db, principal) == "full"
    if mine_only:
        found = [] if principal.employee is None else mine.search_my_guests(db, principal.employee.id, q, full)
    else:
        found = guests.search_guests(db, q, full=full)
    codes = vip_codes.code_texts(db) if any(g.vip_code_id for g in found) else {}
    return [{"id": g.id, "last_name": g.last_name, "first_name": g.first_name,
             "middle_name": g.middle_name, "special": bool(g.special),
             "vip_code_id": g.vip_code_id, "vip_code": codes.get(g.vip_code_id, ("", False))[0],
             "short": guests.short_name(g)}
            for g in found]


def tab(db: Session, principal: Principal, *, q: str, special: bool, vip_code_id: int | None,
        stayed_from: dt.date | None, stayed_to: dt.date | None, birthday_days: int | None, sort: str,
        direction: str, offset: int, limit: int) -> dict:
    """Вкладка «Гости»: только полный уровень, остальным — 403; затем проверка самого запроса (422)."""
    require_full(db, principal)
    query = guests_list.GuestQuery(q, special, vip_code_id, stayed_from, stayed_to, birthday_days, sort,
                                   direction, offset, limit)
    return guests_list.list_guests(db, query)


def get_card(db: Session, principal: Principal, gid: int) -> dict:
    g = _guest(db, gid)
    own_guest(db, principal, gid, "stays.guests")
    return card(db, g)


def stays_of(db: Session, principal: Principal, gid: int) -> list[dict]:
    """История проживаний гостя: все брони, где он жил, с объектами по фонду дня и батлерами."""
    require_full(db, principal)
    _guest(db, gid)
    return history.guest_stays(db, gid)


def prefs(db: Session, principal: Principal, gid: int) -> list[dict]:
    """Пожелания гостя к объекту (часть 2 §5): полный уровень или свой гость батлера."""
    _guest(db, gid)
    if not own_guest(db, principal, gid, "stays.guests"):
        require_full(db, principal)
    return guests.prefs_of(db, gid)


def family(db: Session, principal: Principal, gid: int) -> dict:
    """Семейное дерево (§4): уровень «с фамилиями» и выше; телефоны и даты рождения — только
    полный уровень. Граф — до 3 поколений вверх и вниз и через брак."""
    level = level_for(db, principal)
    if not at_least(level, "names"):
        raise Forbidden("Семейное дерево — с уровня «с фамилиями»")
    _guest(db, gid)
    out = family_graph.family(db, gid, full=at_least(level, "full"))
    for person in out["people"]:            # ниже полного уровня телефона и даты рождения нет — ``None``
        person.setdefault("phone", None)
        person.setdefault("birth_date", None)
    return out
