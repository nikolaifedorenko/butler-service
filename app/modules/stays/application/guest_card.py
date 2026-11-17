"""Карточка гостя в ответах: профиль, его VIP-код, число броней, куда дойдёт смена кода, связи."""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.modules.guests.application import guests
from app.modules.guests.application.catalog import Guest

from . import reservations


def card(db: Session, g: Guest) -> dict:
    return {**guests.guest_dict(g), **reservations.guest_profile_extra(db, g), "links": guests.links_of(db, g.id)}
