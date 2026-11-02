"""Проверка «свой гость» для эндпоинтов профиля (часть 4 §3–§4): одна на все входы — карточку,
профиль, его правку, пожелания и связи."""
from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.auth import Principal

from ..adapters.orm import GuestLink
from ..application import mine


def own_guest(db: Session, principal: Principal, gid: int, full_perm: str) -> bool:
    """С full_perm — любой гость (False). Без него батлер видит и правит только своих гостей
    (stays.mine — чтение, stays.mine_guest_edit — правка): иначе 403; True — режим батлера."""
    if full_perm in principal.gate_permissions:
        return False
    if principal.employee is None or not mine.owns_guest(db, principal.employee.id, gid):
        raise HTTPException(status_code=403, detail="Это не ваш гость: вы не ведёте его брони")
    return True


def own_link(db: Session, principal: Principal, link_id: int) -> None:
    """Правка связи (удалить, «бывшие»): со stays.edit — любой; батлеру — если хотя бы одна сторона
    своя, иначе 403. Нет связи — дальше ответит сама операция (422)."""
    if "stays.edit" in principal.gate_permissions:
        return
    row = db.get(GuestLink, link_id)
    if row is None:
        return
    try:
        if principal.employee is None:
            raise mine.MineForbidden("Это связь чужих гостей: вы не ведёте ни одного из них")
        mine.check_link_change(db, principal.employee.id, row)
    except mine.MineForbidden as e:
        raise HTTPException(status_code=403, detail=str(e)) from e


def my_reservations(db: Session, principal: Principal) -> set[int] | None:
    """Брони батлера для выделения на шахматке: одно множество на запрос. None — у принципала нет
    stays.mine или к учётной записи не привязан сотрудник (признака «своя» в ответе нет)."""
    if "stays.mine" not in principal.gate_permissions or principal.employee is None:
        return None
    return mine.my_reservation_ids(db, principal.employee.id)
