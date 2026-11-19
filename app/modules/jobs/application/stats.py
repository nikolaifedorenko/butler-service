"""Состояние очереди для наблюдения: насколько опаздывают расписания, сколько задач в каждом статусе,
сколько провалилось. По запаздыванию расписания видно, что воркер не работает: пока он жив, срок
следующего запуска каждой периодической задачи лежит в будущем."""
from __future__ import annotations

import datetime as dt
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.time import now as _now

from ..adapters.orm import FAILED, Job, Schedule

# воркер опаздывает, если расписание просрочено больше чем на «три периода» (но не меньше двух минут):
# долгая задача сдвигает следующий оборот, и это не авария
OVERDUE_FACTOR = 3
OVERDUE_MIN_SECONDS = 120


def schedule_lags(db: Session, *, now: Optional[dt.datetime] = None) -> dict[str, float]:
    """Секунды просрочки каждого включённого расписания (0 — срок ещё не наступил)."""
    moment = now or _now()
    rows = db.execute(select(Schedule.name, Schedule.next_run_at).where(Schedule.enabled.is_(True)))
    return {name: max(0.0, (moment - next_run).total_seconds()) for name, next_run in rows}


def overdue(db: Session, *, now: Optional[dt.datetime] = None) -> list[str]:
    """Имена расписаний, просроченных настолько, что воркер, вероятно, не работает."""
    moment = now or _now()
    limits = {name: max(OVERDUE_MIN_SECONDS, OVERDUE_FACTOR * every)
              for name, every in db.execute(select(Schedule.name, Schedule.every_seconds).where(Schedule.enabled.is_(True)))}
    return sorted(name for name, lag in schedule_lags(db, now=moment).items() if lag > limits[name])


def queue_counts(db: Session) -> dict[str, int]:
    """Число задач в каждом статусе (queued, running, done, failed)."""
    counts = {"queued": 0, "running": 0, "done": 0, "failed": 0}
    counts.update(dict(db.execute(select(Job.status, func.count()).group_by(Job.status)).all()))
    return counts


def failed_since(db: Session, hours: int = 24, *, now: Optional[dt.datetime] = None) -> int:
    """Сколько задач окончательно провалилось за последние hours часов."""
    since = (now or _now()) - dt.timedelta(hours=hours)
    return db.scalar(select(func.count()).select_from(Job).where(Job.status == FAILED, Job.finished_at >= since)) or 0
