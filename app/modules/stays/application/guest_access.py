"""Кто что видит и правит в профилях гостей: «свой гость» батлера и полный уровень.

Одна проверка на все входы — карточку, профиль, его правку, пожелания, связи (часть 4 §3–§4).
Отказ — ``Forbidden`` (403) с текстом для пользователя. Право самого эндпоинта
(``stays.mine`` на чтение, ``stays.mine_guest_edit`` на правку) проверяет роутер.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.auth import Principal
from app.core.errors import Forbidden
from app.modules.guests.application.catalog import GuestLink

from . import mine


def butler_id(principal: Principal) -> int:
    """Сотрудник-батлер принципала; режим батлера без карточки сотрудника — отказ."""
    if principal.employee is None:
        raise mine.MineForbidden("Учётная запись не связана с сотрудником")
    return principal.employee.id


def own_guest(db: Session, principal: Principal, gid: int, full_perm: str) -> bool:
    """С ``full_perm`` — любой гость (False). Без него — только свой гость принципала, иначе
    отказ; True — режим батлера."""
    if full_perm in principal.gate_permissions:
        return False
    if principal.employee is None or not mine.owns_guest(db, principal.employee.id, gid):
        raise mine.MineForbidden("Это не ваш гость: вы не ведёте его брони")
    return True


def own_link(db: Session, principal: Principal, link_id: int) -> None:
    """Правка связи (удалить, «бывшие»): со ``stays.edit`` — любой; батлеру — если хотя бы одна
    сторона своя, иначе отказ. Нет связи — дальше ответит сама операция (422)."""
    if "stays.edit" in principal.gate_permissions:
        return
    row = db.get(GuestLink, link_id)
    if row is None:
        return
    if principal.employee is None:
        raise mine.MineForbidden("Это связь чужих гостей: вы не ведёте ни одного из них")
    mine.check_link_change(db, principal.employee.id, row)


def require_full(db: Session, principal: Principal) -> None:
    """Раздел «Гости» и всё, что из него (addendum §3): право ``stays.guests`` самостоятельно."""
    perms = getattr(principal, "gate_permissions", None) or ()
    if "stays.guests" not in perms:
        raise Forbidden("Справочник гостей — с правом «Профили гостей целиком»")


def my_reservations(db: Session, principal: Principal) -> set[int] | None:
    """Брони батлера для выделения на шахматке: одно множество на запрос. ``None`` — у принципала
    нет ``stays.mine`` или к учётной записи не привязан сотрудник (признака «своя» в ответе нет)."""
    if "stays.mine" not in principal.gate_permissions or principal.employee is None:
        return None
    return mine.my_reservation_ids(db, principal.employee.id)
