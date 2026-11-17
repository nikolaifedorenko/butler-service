"""Карточка гостя в ответах: профиль, его VIP-код, число броней, куда дойдёт смена кода, связи."""
from __future__ import annotations

from sqlalchemy.orm import Session

from ..adapters.orm import Guest
from . import guests, reservations


def card(db: Session, g: Guest) -> dict:
    return {**guests.guest_dict(g), **reservations.guest_profile_extra(db, g), "links": guests.links_of(db, g.id)}
