"""Проверка «свой гость» для эндпоинтов профиля (часть 4 §3–§4): правила — в прикладном слое
(``application/guest_access.py``), здесь они доступны под прежними именами остальным роутерам."""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.auth import Principal

from ..application import mine
from ..application.guest_access import own_guest, own_link

__all__ = ["my_reservations", "own_guest", "own_link"]


def my_reservations(db: Session, principal: Principal) -> set[int] | None:
    """Брони батлера для выделения на шахматке: одно множество на запрос. None — у принципала нет
    stays.mine или к учётной записи не привязан сотрудник (признака «своя» в ответе нет)."""
    if "stays.mine" not in principal.gate_permissions or principal.employee is None:
        return None
    return mine.my_reservation_ids(db, principal.employee.id)
