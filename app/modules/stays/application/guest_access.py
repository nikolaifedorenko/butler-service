"""Кто что видит и правит в профилях гостей: «свой гость» батлера и полный уровень.

Одна проверка на все входы — карточку, профиль, его правку, пожелания, связи (часть 4 §3–§4).
Отказ — ``Forbidden`` (403) с текстом для пользователя. Право самого эндпоинта
(``stays.mine`` на чтение, ``stays.mine_guest_edit`` на правку) проверяет роутер.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.auth import Principal
from app.core.errors import Forbidden

from ..adapters.orm import GuestLink
from . import mine
from .visibility import level_for


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
    """Вкладка «Гости» и всё, что из неё (addendum §3): только полный уровень — ``stays.guests``
    вместе с доступом к шахматке с фамилиями."""
    if level_for(db, principal) != "full":
        raise Forbidden("Справочник гостей — с правом «Профили гостей целиком»")
