"""Очередь задач и расписание. Кросс-модульных связей нет: задача называется строкой — именем из
манифеста модуля-владельца, а нагрузка — произвольный JSON."""
from __future__ import annotations

import datetime as dt
from typing import Optional

from sqlalchemy import Boolean, CheckConstraint, Index, Integer, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, Json
from app.core.time import Moment, now

QUEUED, RUNNING, DONE, FAILED = "queued", "running", "done", "failed"


class Job(Base):
    """Одна задача очереди. ``queued`` — ждёт ``run_at``; ``running`` — взята воркером на срок
    ``locked_until``; ``done`` и ``failed`` — конечные. Из расписания задача создаётся с
    ``schedule_name``: у одного расписания не бывает двух незавершённых задач."""

    __tablename__ = "jobs_queue"
    __table_args__ = (
        CheckConstraint("status IN ('queued', 'running', 'done', 'failed')", name="ck_jobs_queue_status"),
        Index("ix_jobs_queue_due", "status", "run_at"),
        Index("uq_jobs_queue_schedule_open", "schedule_name", unique=True,
              postgresql_where=text("schedule_name IS NOT NULL AND status IN ('queued', 'running')")),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80))
    payload: Mapped[dict] = mapped_column(Json, default=dict)
    status: Mapped[str] = mapped_column(String(8), default=QUEUED)
    run_at: Mapped[dt.datetime] = mapped_column(Moment, default=now)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3)
    locked_until: Mapped[Optional[dt.datetime]] = mapped_column(Moment, nullable=True)
    schedule_name: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    last_error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[dt.datetime] = mapped_column(Moment, default=now)
    started_at: Mapped[Optional[dt.datetime]] = mapped_column(Moment, nullable=True)
    finished_at: Mapped[Optional[dt.datetime]] = mapped_column(Moment, nullable=True)


class Schedule(Base):
    """Повторяющаяся задача: раз в ``every_seconds`` в очередь кладётся задача с именем расписания."""

    __tablename__ = "jobs_schedule"

    name: Mapped[str] = mapped_column(String(80), primary_key=True)
    every_seconds: Mapped[int] = mapped_column(Integer)
    next_run_at: Mapped[dt.datetime] = mapped_column(Moment, default=now)
    last_run_at: Mapped[Optional[dt.datetime]] = mapped_column(Moment, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
