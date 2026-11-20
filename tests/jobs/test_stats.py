"""Наблюдение за очередью: просрочка расписаний, счётчики статусов, проверка воркера и метрики."""
from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy import delete

from app.bootstrap import jobs_worker
from app.bootstrap.metrics import StateCollector
from app.modules.jobs.adapters.orm import FAILED, QUEUED, Job, Schedule
from app.modules.jobs.application import stats

T0 = dt.datetime(2030, 1, 1, 12, 0, tzinfo=dt.UTC)


def at(seconds: float = 0) -> dt.datetime:
    return T0 + dt.timedelta(seconds=seconds)


@pytest.fixture(autouse=True)
def _clean(db):
    def wipe():
        db.rollback()
        db.execute(delete(Job))
        db.execute(delete(Schedule))
        db.commit()
    wipe()
    yield
    wipe()


def _schedule(db, name, every, next_run, enabled=True):
    db.add(Schedule(name=name, every_seconds=every, next_run_at=next_run, enabled=enabled))
    db.commit()


def test_lag_is_zero_until_due_and_grows_after(db):
    _schedule(db, "night_sync", 60, at(30))
    _schedule(db, "media_cleanup", 86400, at(-500))
    _schedule(db, "off", 60, at(-9999), enabled=False)
    lags = stats.schedule_lags(db, now=T0)
    assert lags == {"night_sync": 0.0, "media_cleanup": 500.0}, "отключённые расписания не считаются"


def test_overdue_needs_more_than_three_periods(db):
    _schedule(db, "fast", 60, at(-170))        # предел max(120, 180) = 180 с: ещё в срок
    _schedule(db, "stuck", 60, at(-200))       # просрочено больше предела
    _schedule(db, "daily", 86400, at(-86400))  # сутки просрочки при пределе трое суток — не авария
    assert stats.overdue(db, now=T0) == ["stuck"]


def test_queue_counts_and_recent_failures(db):
    db.add_all([Job(name="a", status=QUEUED, run_at=T0),
                Job(name="b", status=FAILED, run_at=T0, finished_at=at(-3600)),
                Job(name="c", status=FAILED, run_at=T0, finished_at=at(-3 * 86400))])
    db.commit()
    assert stats.queue_counts(db) == {"queued": 1, "running": 0, "done": 0, "failed": 2}
    assert stats.failed_since(db, 24, now=T0) == 1


def test_worker_check_reports_state(db, capsys):
    from app.core.time import now

    _schedule(db, "night_sync", 60, now() + dt.timedelta(seconds=30))
    assert jobs_worker.check() == 0 and "ok" in capsys.readouterr().out
    db.execute(delete(Schedule))
    _schedule(db, "night_sync", 60, now() - dt.timedelta(hours=1))
    assert jobs_worker.check() == 1 and "night_sync" in capsys.readouterr().out


def test_state_collector_exposes_queue_and_pdf(db):
    from app.core.time import now

    _schedule(db, "night_sync", 60, now() - dt.timedelta(hours=1))
    names = {m.name: m for m in StateCollector().collect()}
    assert {"tt_jobs_schedule_lag_seconds", "tt_jobs_queue", "tt_jobs_failed_24h", "tt_jobs_overdue",
            "tt_pdf_available"} <= set(names)
    assert names["tt_jobs_overdue"].samples[0].value == 1
    assert names["tt_jobs_schedule_lag_seconds"].samples[0].labels == {"job": "night_sync"}
