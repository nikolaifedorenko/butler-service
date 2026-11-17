"""Расписание: периодические задачи модулей и их постановка в очередь.

Расписание — строки ``jobs_schedule``, которые ``sync`` приводит к списку из манифестов. ``tick`` кладёт
в очередь задачи тех, у кого срок наступил; у одного расписания не бывает двух незавершённых задач
(частичный уникальный индекс), поэтому медленная задача не копит очередь. Несколько воркеров
тикают без гонок: строки расписания берутся ``FOR UPDATE SKIP LOCKED``.
"""
from __future__ import annotations

import datetime as dt
from collections.abc import Sequence
from typing import Optional

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.core.manifest import JobSpec
from app.core.time import now as _now

from ..adapters.orm import QUEUED, Job, Schedule


def sync(db: Session, specs: Sequence[JobSpec], *, now: Optional[dt.datetime] = None) -> None:
    """Привести расписание к списку задач с периодом: новые — запускаются сразу, изменённый период
    обновляется, исчезнувшие — отключаются (история остаётся)."""
    moment = now or _now()
    wanted = {s.name: s for s in specs if s.every_seconds}
    have = {r.name: r for r in db.scalars(select(Schedule))}
    for name, spec in wanted.items():
        row = have.get(name)
        if row is None:
            db.add(Schedule(name=name, every_seconds=spec.every_seconds, next_run_at=moment, enabled=True))
        else:
            row.every_seconds = spec.every_seconds
            row.enabled = True
    for name, row in have.items():
        if name not in wanted:
            row.enabled = False
    db.commit()


def tick(db: Session, specs: Sequence[JobSpec], *, now: Optional[dt.datetime] = None) -> int:
    """Положить в очередь задачи расписаний, чей срок наступил. Возвращает, сколько поставлено."""
    moment = now or _now()
    by_name = {s.name: s for s in specs}
    due = list(db.scalars(select(Schedule).where(Schedule.enabled.is_(True), Schedule.next_run_at <= moment)
                          .order_by(Schedule.next_run_at).with_for_update(skip_locked=True)))
    put = 0
    for row in due:
        spec = by_name.get(row.name)
        if spec is not None:
            added = db.execute(pg_insert(Job).values(
                name=row.name, payload={}, status=QUEUED, run_at=moment, attempts=0,
                max_attempts=spec.max_attempts, schedule_name=row.name, last_error="", created_at=moment,
            ).on_conflict_do_nothing(index_elements=["schedule_name"],
                                     index_where=(Job.schedule_name.is_not(None)) & Job.status.in_(("queued", "running"))))
            put += added.rowcount or 0
        row.last_run_at = moment
        row.next_run_at = moment + dt.timedelta(seconds=row.every_seconds)
    db.commit()
    return put
