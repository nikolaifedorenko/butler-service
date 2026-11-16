"""Операция шахматки «с предпросмотром»: тот же код показывает разницу и сохраняет (§4.6).

Предпросмотр выполняет операцию целиком и откатывает её; сохранение фиксирует. Новый
овербукинг без права ``stays.overbook`` не сохраняется: отказ 409 несёт предпросмотр
(``detail.diff``); сам предпросмотр отвечает обычным ответом с ``overbook_refused`` — текстом,
почему не сохранится (часть 2 §7).
"""
from __future__ import annotations

import datetime as dt
from collections.abc import Callable
from typing import Any

from sqlalchemy.orm import Session

from app.core.db import transaction
from app.core.errors import Conflict

from ..ports.duty import DutyPort
from . import preview


class OverbookRefusedError(Conflict):
    """Сохранение оставило бы бронь без объекта, а права «Овербукинг» нет → 409."""

    def __init__(self, text: str, diff: dict):
        super().__init__(text)
        self.diff = diff

    @property
    def detail(self) -> dict:
        return {"message": self.message, "overbook": True, "diff": self.diff}


class _Discard(Exception):
    """Служебный выход из транзакции: откатить всё, что записано внутри."""


def discarded[T](db: Session, action: Callable[[], T]) -> T:
    """Выполнить ``action`` и отменить все её записи. Результат ``action`` должен быть уже
    готовым словарём: после отката ORM-объекты просрочены."""
    box: list[T] = []
    try:
        with transaction(db):
            box.append(action())
            raise _Discard
    except _Discard:
        pass
    return box[0]


def run_previewed(db: Session, operation: Callable[[], Any], *, preview_only: bool, may_overbook: bool,
                  window: tuple[dt.date, dt.date] | None = None, duty: DutyPort | None = None) -> dict:
    """``{"preview", "result", "diff", "overbook_refused"}`` (последнее — ``None``, если отказа нет). ``operation`` пишет и журнал
    аудита и возвращает сериализованный результат."""
    refused: str | None = None

    def attempt() -> tuple[Any, dict]:
        nonlocal refused
        try:
            result, diff = preview.run_operation(db, operation, window, duty, may_overbook=may_overbook)
        except preview.OverbookRefused as e:
            if not preview_only:
                raise OverbookRefusedError(e.text, e.diff) from e
            refused = e.text
            return e.result, e.diff
        return result, diff

    if preview_only:
        result, diff = discarded(db, attempt)
    else:
        with transaction(db):
            result, diff = attempt()
    return {"preview": preview_only, "result": result, "diff": diff, "overbook_refused": refused}
