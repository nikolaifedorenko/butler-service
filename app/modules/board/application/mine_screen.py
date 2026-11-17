"""«Мои гости» батлера: «Сегодня», «Мой месяц», все свои гости, карточка своего гостя (часть 4 §5).

Нужно ``stays.mine`` и сотрудник, привязанный к учётной записи; чужой гость — 403.
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy.orm import Session

from app.core.auth import Principal
from app.core.errors import NotFound
from app.modules.guests.application.catalog import Guest
from app.modules.stays.application import mine
from app.modules.stays.application.visibility import level_for
from app.modules.stays.ports.duty import DutyPort


def _me(principal: Principal) -> int:
    if principal.employee is None:
        raise NotFound("К учётной записи не привязан сотрудник")
    return principal.employee.id


def today_reservations(db: Session, principal: Principal) -> dict:
    """Брони, где батлер ведёт гостей в эту ночь."""
    return mine.mine_today(db, _me(principal))


def month(db: Session, principal: Principal, first: dt.date, last: dt.date, duty: DutyPort) -> dict:
    """Свои брони полосами, нагрузка по дням и отсутствия по Графику (не больше 62 дней)."""
    return mine.mine_month(db, _me(principal), first, last, duty)


def guests(db: Session, principal: Principal, q: str, offset: int, limit: int) -> dict:
    """Свои гости за всё время, поиск по ФИО (с полным уровнем — как подбор гостя), по 50."""
    return mine.mine_guests(db, _me(principal), q, offset, limit, full=level_for(db, principal) == "full")


def guest_card(db: Session, principal: Principal, gid: int) -> dict:
    """Профиль целиком и история проживаний с тем, кто гостя вёл."""
    me = _me(principal)
    g = db.get(Guest, gid)
    if g is None:
        raise NotFound("Гость не найден")
    if not mine.owns_guest(db, me, gid):
        raise mine.MineForbidden("Это не ваш гость: вы не ведёте его брони")
    return mine.mine_guest_card(db, me, g)
