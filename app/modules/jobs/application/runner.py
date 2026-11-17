"""Исполнитель: берёт готовые задачи и вызывает их обработчики.

Обработчик — функция ``(db, payload)``; ей дают собственную сессию, успех фиксирует запись обработчика,
исключение откатывает её и возвращает задачу в очередь с паузой (или отказывает по числу попыток).
Состояние задачи ведётся отдельной сессией: падение обработчика не теряет учёт.
"""
from __future__ import annotations

import datetime as dt
import logging
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.core.db import transaction

from . import queue

log = logging.getLogger("uvicorn.error")

Handler = Callable[[Session, dict], Any]


@dataclass
class Report:
    done: int = 0
    retried: int = 0
    failed: int = 0

    @property
    def ran(self) -> int:
        return self.done + self.retried + self.failed


def run_pending(session_factory: Callable[[], Session], handlers: Mapping[str, Handler], *,
                now: Optional[Callable[[], dt.datetime]] = None, limit: int = 100,
                lease_seconds: int = queue.DEFAULT_LEASE_SECONDS) -> Report:
    """Выполнить готовые задачи, не больше ``limit`` за раз. Задача с неизвестным именем — отказ
    без повторов: повтор её не починит."""
    report = Report()
    clock = now or queue.now_moment
    for _ in range(limit):
        with session_factory() as control:
            job = queue.claim_next(control, now=clock(), lease_seconds=lease_seconds)
            if job is None:
                break
            handler = handlers.get(job.name)
            if handler is None:
                queue.fail(control, job.id, f"нет обработчика задачи «{job.name}»", now=clock(), permanent=True)
                report.failed += 1
                continue
            error = _run(session_factory, handler, job.payload, job.name)
            if error is None:
                queue.finish(control, job.id, now=clock())
                report.done += 1
            elif queue.fail(control, job.id, error, now=clock()) == "failed":
                report.failed += 1
            else:
                report.retried += 1
    return report


def _run(session_factory: Callable[[], Session], handler: Handler, payload: dict, name: str) -> Optional[str]:
    """Вызвать обработчик в своей сессии; текст ошибки или None."""
    with session_factory() as db:
        try:
            with transaction(db):                        # успех фиксирует записи обработчика, ошибка откатывает
                handler(db, payload)
        except Exception as exc:                         # обработчик не должен ронять воркер
            log.exception("jobs: задача «%s» завершилась ошибкой", name)
            return f"{type(exc).__name__}: {exc}"
    return None
