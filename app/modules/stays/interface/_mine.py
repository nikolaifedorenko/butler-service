"""Проверки «свой гость» и «своя бронь» для эндпоинтов шахматки (часть 4 §3–§4): правила — в
прикладном слое (``application/guest_access.py``), здесь они доступны под прежними именами
остальным роутерам."""
from __future__ import annotations

from ..application.guest_access import my_reservations, own_guest, own_link

__all__ = ["my_reservations", "own_guest", "own_link"]
