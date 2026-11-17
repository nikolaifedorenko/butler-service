"""Очередь: положить задачу, взять следующую, отметить результат, вернуть зависшие.

Взятие — ``SELECT … FOR UPDATE SKIP LOCKED``: несколько воркеров не берут одну задачу и не ждут
друг друга. Ничего, кроме собственных строк очереди, модуль не трогает; ``commit`` здесь — граница
операции очереди (каждая фиксируется сразу: задачу видят все воркеры).
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Any, Optional

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.time import now as _now

from ..adapters.orm import DONE, FAILED, QUEUED, RUNNING, Job
from ..domain.retry import retry_delay

now_moment = _now                     # текущий момент; подменяется в тестах
DEFAULT_LEASE_SECONDS = 900
STALE_ERROR = "воркер не завершил задачу в срок (процесс прерван?)"


@dataclass(frozen=True)
class Claimed:
    """Взятая в работу задача: данные, а не строка ORM — после фиксации сессия её просрочит."""

    id: int
    name: str
    payload: dict
    attempts: int
    max_attempts: int


def enqueue(db: Session, name: str, payload: Optional[dict[str, Any]] = None, *, run_at: Optional[dt.datetime] = None,
            max_attempts: int = 3, schedule_name: Optional[str] = None) -> int:
    """Положить задачу в очередь; возвращает её номер. Фиксирует транзакцию вызывающего: так
    задача не пропадёт, если после постановки процесс упадёт."""
    job = Job(name=name, payload=dict(payload or {}), run_at=run_at or _now(), max_attempts=max_attempts,
              schedule_name=schedule_name)
    db.add(job)
    db.commit()
    return job.id


def claim_next(db: Session, *, now: Optional[dt.datetime] = None, lease_seconds: int = DEFAULT_LEASE_SECONDS,
               commit: bool = True) -> Optional[Claimed]:
    """Взять самую раннюю готовую задачу (``queued`` и ``run_at`` наступил) на срок ``lease_seconds``;
    нет готовых — None. ``commit=False`` оставляет взятие в открытой транзакции (для проверки замков)."""
    moment = now or _now()
    job = db.scalars(select(Job).where(Job.status == QUEUED, Job.run_at <= moment)
                     .order_by(Job.run_at, Job.id).limit(1).with_for_update(skip_locked=True)).first()
    if job is None:
        db.rollback()
        return None
    job.status = RUNNING
    job.attempts += 1
    job.started_at = moment
    job.locked_until = moment + dt.timedelta(seconds=lease_seconds)
    taken = Claimed(job.id, job.name, dict(job.payload or {}), job.attempts, job.max_attempts)
    if commit:
        db.commit()
    else:
        db.flush()
    return taken


def finish(db: Session, job_id: int, *, now: Optional[dt.datetime] = None) -> None:
    """Задача выполнена."""
    db.execute(update(Job).where(Job.id == job_id).values(
        status=DONE, finished_at=now or _now(), locked_until=None))
    db.commit()


def fail(db: Session, job_id: int, error: str, *, now: Optional[dt.datetime] = None, base_delay: int = 30,
         permanent: bool = False) -> str:
    """Попытка не удалась: есть ещё попытки — задача вернётся в очередь через паузу, иначе — отказ
    (``permanent`` — сразу отказ: повтор не поможет). Возвращает новый статус."""
    moment = now or _now()
    job = db.get(Job, job_id)
    if job is None:
        return FAILED
    job.last_error = error[:4000]
    job.locked_until = None
    if job.attempts < job.max_attempts and not permanent:
        job.status = QUEUED
        job.run_at = moment + dt.timedelta(seconds=retry_delay(job.attempts, base_delay))
    else:
        job.status = FAILED
        job.finished_at = moment
    status = job.status
    db.commit()
    return status


def requeue_stale(db: Session, *, now: Optional[dt.datetime] = None) -> int:
    """Вернуть задачи, которые воркер взял и не закончил (срок захвата вышел): ещё есть попытки — в
    очередь, иначе — отказ. Возвращает, сколько задач тронуто."""
    moment = now or _now()
    stale = list(db.scalars(select(Job).where(Job.status == RUNNING, Job.locked_until < moment)
                            .with_for_update(skip_locked=True)))
    for job in stale:
        job.last_error = STALE_ERROR
        job.locked_until = None
        if job.attempts < job.max_attempts:
            job.status = QUEUED
            job.run_at = moment
        else:
            job.status = FAILED
            job.finished_at = moment
    db.commit()
    return len(stale)
