"""Чтение профилей гостей: подбор, раздел «Гости», карточка, история, пожелания, семья (§3.2, §4, §8).

Список с фамилиями — ``stays.view``, карточка целиком — ``stays.guests``; батлер (часть 4 §3) —
только свои гости. Роутер проверяет право эндпоинта, остальные проверки — здесь.
"""
from __future__ import annotations

import datetime as dt
from typing import Literal

from sqlalchemy.orm import Session

from app.core.auth import Principal
from app.core.errors import Forbidden, NotFound
from app.modules.guests.application import family as family_graph
from app.modules.guests.application import guests, vip_codes
from app.modules.guests.application.catalog import Guest
from app.modules.stays.application import guests_list, history, mine
from app.modules.stays.application.guest_access import own_guest, require_full
from app.modules.stays.application.guest_card import card
from app.modules.stays.application.visibility import Level, at_least, level_for


def _guest(db: Session, gid: int) -> Guest:
    g = db.get(Guest, gid)
    if g is None:
        raise NotFound("Гость не найден")
    return g


def search(db: Session, principal: Principal, q: str, mine_only: bool, *, details: bool = False) -> list[dict]:
    """Телефон и дата рождения для подбора запрашиваются с details=1 и полным доступом к профилям.
    Полный уровень ищет по ФИО, телефону, дате рождения, почте и полям с поиском.
    Ниже полного уровня поиск только по ФИО (решение 8).
    ``mine_only`` — только свои гости батлера (редактор связей, часть 4 §3)."""
    full = "stays.guests" in principal.gate_permissions
    if mine_only:
        found = [] if principal.employee is None else mine.search_my_guests(db, principal.employee.id, q, full)
    else:
        found = guests.search_guests(db, q, full=full)
    codes = vip_codes.code_texts(db) if any(g.vip_code_id for g in found) else {}
    return [{"id": g.id, "last_name": g.last_name, "first_name": g.first_name,
             "middle_name": g.middle_name, "special": bool(g.special),
             "vip_code_id": g.vip_code_id, "vip_code": codes.get(g.vip_code_id or 0, ("", False))[0],
             "short": guests.short_name(g),
             **({"phone": guests.format_phone(g.phone) or None, "birth_date": g.birth_date}
                if details and full else {})}
            for g in found]


def tab(db: Session, principal: Principal, *, q: str, special: bool, vip_code_id: int | None,
        stayed_from: dt.date | None, stayed_to: dt.date | None, birthday_days: int | None, sort: str,
        direction: Literal["asc", "desc"], offset: int, limit: int) -> dict:
    """Раздел «Гости»: только полный уровень, остальным — 403; затем проверка самого запроса (422)."""
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


def family(db: Session, principal: Principal, gid: int, *, focus_id: int | None = None) -> dict:
    """Семейное дерево (§4): уровень «с фамилиями» и выше; телефоны и даты рождения — только
    полный уровень. Граф — до 3 поколений вверх и вниз и через брак."""
    level: Level | None
    if "stays.guests" in principal.gate_permissions:
        level = "full"
    else:
        level = level_for(db, principal)
    if not at_least(level, "names") and "stays.mine_guest_edit" in principal.gate_permissions:
        own_guest(db, principal, gid, "stays.guests")
        level = "names"
    if not at_least(level, "names"):
        raise Forbidden("Семейное дерево — с уровня «с фамилиями»")
    _guest(db, gid)
    out = family_graph.family(db, gid, full=at_least(level, "full"), focus_id=focus_id)
    perms = principal.gate_permissions
    full_card = "stays.guests" in perms
    full_edit = "stays.edit" in perms
    mine_edit = "stays.mine_guest_edit" in perms
    owned = (mine.owned_among(db, principal.employee.id, {p["id"] for p in out["people"]})
             if principal.employee is not None and (mine_edit or "stays.mine" in perms) else set())
    for person in out["people"]:
        person.setdefault("phone", None)
        person.setdefault("birth_date", None)
        person["can_open_card"] = full_card or (person["id"] in owned)
        person["editable"] = full_edit or (mine_edit and person["id"] in owned)
    for link in out["links"]:
        shares_owned_guest = link["a"] in owned or link["b"] in owned
        link["editable"] = full_edit or (mine_edit and shares_owned_guest)
        if not (full_card or full_edit or shares_owned_guest):
            link["marriage_start"] = link["marriage_end"] = None
    return out
