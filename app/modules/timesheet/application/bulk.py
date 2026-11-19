"""Массовая правка «всё или ничего».

Табель — первичный документ: заполненный наполовину хуже незаполненного. Если хотя бы
один день не записался, операция отменяет все свои записи и возвращает полный перечень
отказов — обычным ответом, а не ошибкой."""
from __future__ import annotations

from typing import Callable

from sqlalchemy.orm import Session

from app.core.db import transaction


class NothingWritten(Exception):
    """Массовая правка отменяет свои записи; ``result`` — ответ с перечнем отказов."""

    def __init__(self, result: dict):
        self.result = result
        super().__init__("массовая правка отменена")


def all_or_nothing(db: Session, work: Callable[[], dict]) -> dict:
    """Выполнить ``work`` одной транзакцией; ``NothingWritten`` внутри — откат и её ответ."""
    try:
        with transaction(db):
            return work()
    except NothingWritten as refused:
        return refused.result
