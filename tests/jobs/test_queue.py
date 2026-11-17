"""Очередь задач (ADR-0013, §6): взятие без гонок, повторы с паузой, зависшие, расписание, исполнитель."""
from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy import delete, select

from app.core.db import SessionLocal
from app.core.manifest import JobSpec
from app.modules.jobs.adapters.orm import DONE, FAILED, QUEUED, RUNNING, Job, Schedule
from app.modules.jobs.application import queue, runner, schedule
from app.modules.jobs.domain.retry import retry_delay

T0 = dt.datetime(2030, 1, 1, 12, 0, tzinfo=dt.UTC)


def at(seconds: float = 0) -> dt.datetime:
    return T0 + dt.timedelta(seconds=seconds)


@pytest.fixture(autouse=True)
def _clean_queue(db):
    def wipe():
        db.rollback()
        db.execute(delete(Job))
        db.execute(delete(Schedule))
        db.commit()
    wipe()
    yield
    wipe()


def _job(db, job_id: int) -> Job:
    db.expire_all()
    return db.get(Job, job_id)


# ── пауза перед повтором ────────────────────────────────────────────────────

def test_retry_delay_doubles_and_is_capped():
    assert [retry_delay(n, base=30, cap=3600) for n in (1, 2, 3, 4)] == [30, 60, 120, 240]
    assert retry_delay(50, base=30, cap=3600) == 3600
    with pytest.raises(ValueError):
        retry_delay(0)


# ── очередь ─────────────────────────────────────────────────────────────────

def test_claim_takes_earliest_ready_job_and_marks_it_running(db):
    late = queue.enqueue(db, "a", run_at=at(60))
    first = queue.enqueue(db, "a", {"x": 1}, run_at=at(-60))
    queue.enqueue(db, "a", run_at=at(-30))
    taken = queue.claim_next(db, now=at(0), lease_seconds=100)
    assert (taken.id, taken.payload, taken.attempts) == (first, {"x": 1}, 1)
    job = _job(db, first)
    assert job.status == RUNNING and job.locked_until == at(100) and job.started_at == at(0)
    assert _job(db, late).status == QUEUED                      # срок ещё не наступил


def test_claim_returns_none_when_nothing_is_ready(db):
    queue.enqueue(db, "a", run_at=at(60))
    assert queue.claim_next(db, now=at(0)) is None


def test_two_sessions_never_take_the_same_job(db):
    """Первый воркер ещё не зафиксировал взятие — второй пропускает занятую строку, а не ждёт её."""
    one = queue.enqueue(db, "a", run_at=at(-10))
    two = queue.enqueue(db, "a", run_at=at(-5))
    with SessionLocal() as s1, SessionLocal() as s2:
        a = queue.claim_next(s1, now=at(0), commit=False)
        b = queue.claim_next(s2, now=at(0), commit=False)
        assert {a.id, b.id} == {one, two}
        assert queue.claim_next(s2, now=at(0), commit=False) is None      # свободных больше нет
        s1.rollback()
        s2.rollback()


def test_finish_marks_done(db):
    job_id = queue.enqueue(db, "a", run_at=at(-1))
    queue.claim_next(db, now=at(0))
    queue.finish(db, job_id, now=at(5))
    job = _job(db, job_id)
    assert job.status == DONE and job.finished_at == at(5) and job.locked_until is None


def test_failed_attempt_returns_job_to_queue_with_pause_until_attempts_run_out(db):
    job_id = queue.enqueue(db, "a", run_at=at(-1), max_attempts=3)
    queue.claim_next(db, now=at(0))
    assert queue.fail(db, job_id, "сбой 1", now=at(0), base_delay=30) == QUEUED
    job = _job(db, job_id)
    assert job.run_at == at(30) and job.last_error == "сбой 1" and job.attempts == 1
    assert queue.claim_next(db, now=at(10)) is None                 # пауза ещё идёт
    queue.claim_next(db, now=at(31))
    assert queue.fail(db, job_id, "сбой 2", now=at(31), base_delay=30) == QUEUED
    assert _job(db, job_id).run_at == at(31 + 60)                  # пауза удвоилась
    queue.claim_next(db, now=at(100))
    assert queue.fail(db, job_id, "сбой 3", now=at(100)) == FAILED
    assert _job(db, job_id).finished_at == at(100)


def test_permanent_failure_skips_remaining_attempts(db):
    job_id = queue.enqueue(db, "a", run_at=at(-1), max_attempts=5)
    queue.claim_next(db, now=at(0))
    assert queue.fail(db, job_id, "нет обработчика", now=at(0), permanent=True) == FAILED


def test_stale_running_jobs_return_to_queue_or_fail(db):
    retry = queue.enqueue(db, "a", run_at=at(-1), max_attempts=2)
    last = queue.enqueue(db, "a", run_at=at(-1), max_attempts=1)
    queue.claim_next(db, now=at(0), lease_seconds=60)
    queue.claim_next(db, now=at(0), lease_seconds=60)
    assert queue.requeue_stale(db, now=at(30)) == 0                 # срок захвата не вышел
    assert queue.requeue_stale(db, now=at(61)) == 2
    assert _job(db, retry).status == QUEUED and _job(db, last).status == FAILED
    assert _job(db, retry).last_error == queue.STALE_ERROR


# ── расписание ──────────────────────────────────────────────────────────────

SPECS = [JobSpec("night_sync", "x:y", every_seconds=60, max_attempts=2), JobSpec("on_demand", "x:z")]


def test_sync_adds_changes_and_disables_schedules(db):
    schedule.sync(db, SPECS, now=at(0))
    rows = {r.name: r for r in db.scalars(select(Schedule))}
    assert set(rows) == {"night_sync"} and rows["night_sync"].next_run_at == at(0)   # без периода — не по расписанию
    schedule.sync(db, [JobSpec("night_sync", "x:y", every_seconds=120)], now=at(10))
    db.expire_all()
    assert db.get(Schedule, "night_sync").every_seconds == 120
    schedule.sync(db, [], now=at(20))
    db.expire_all()
    assert db.get(Schedule, "night_sync").enabled is False


def test_tick_enqueues_due_schedule_once_and_moves_next_run(db):
    schedule.sync(db, SPECS, now=at(0))
    assert schedule.tick(db, SPECS, now=at(0)) == 1
    job = db.scalars(select(Job)).one()
    assert (job.name, job.schedule_name, job.max_attempts, job.status) == ("night_sync", "night_sync", 2, QUEUED)
    db.expire_all()
    sched = db.get(Schedule, "night_sync")
    assert sched.last_run_at == at(0) and sched.next_run_at == at(60)
    assert schedule.tick(db, SPECS, now=at(30)) == 0                 # срок не наступил


def test_unfinished_schedule_job_is_not_duplicated(db):
    schedule.sync(db, SPECS, now=at(0))
    schedule.tick(db, SPECS, now=at(0))
    assert schedule.tick(db, SPECS, now=at(61)) == 0                 # прошлая ещё в очереди
    assert len(list(db.scalars(select(Job)))) == 1
    taken = queue.claim_next(db, now=at(62))
    queue.finish(db, taken.id, now=at(63))
    assert schedule.tick(db, SPECS, now=at(125)) == 1                # прошлая закончена — новая можно
    assert len(list(db.scalars(select(Job)))) == 2


def test_disabled_schedule_is_skipped(db):
    schedule.sync(db, SPECS, now=at(0))
    schedule.sync(db, [], now=at(1))
    assert schedule.tick(db, SPECS, now=at(100)) == 0


# ── исполнитель ─────────────────────────────────────────────────────────────

def test_runner_runs_handlers_and_marks_results(db):
    seen: list[dict] = []
    ok = queue.enqueue(db, "ok", {"n": 1}, run_at=at(-1))
    bad = queue.enqueue(db, "bad", run_at=at(-1), max_attempts=1)
    unknown = queue.enqueue(db, "ghost", run_at=at(-1), max_attempts=5)

    def boom(_db, _payload):
        raise RuntimeError("не вышло")
    report = runner.run_pending(SessionLocal, {"ok": lambda _db, p: seen.append(p), "bad": boom}, now=lambda: at(0))
    assert (report.done, report.failed, report.retried) == (1, 2, 0)
    assert seen == [{"n": 1}]
    assert _job(db, ok).status == DONE
    assert _job(db, bad).status == FAILED and "RuntimeError: не вышло" in _job(db, bad).last_error
    assert _job(db, unknown).status == FAILED and "нет обработчика" in _job(db, unknown).last_error


def test_runner_retries_a_failing_handler_with_pause(db):
    job_id = queue.enqueue(db, "flaky", run_at=at(-1), max_attempts=3)

    def flaky(_db, _payload):
        raise ValueError("временно")
    report = runner.run_pending(SessionLocal, {"flaky": flaky}, now=lambda: at(0))
    assert (report.done, report.retried, report.failed) == (0, 1, 0)
    assert _job(db, job_id).status == QUEUED and _job(db, job_id).run_at == at(30)
    assert runner.run_pending(SessionLocal, {"flaky": flaky}, now=lambda: at(10)).ran == 0     # пауза


def test_failed_handler_rolls_back_its_own_writes(db):
    marker = queue.enqueue(db, "writer", run_at=at(-1), max_attempts=1)

    def writer(handler_db, _payload):
        handler_db.add(Job(name="side-effect", payload={}))
        handler_db.flush()
        raise RuntimeError("после записи")
    runner.run_pending(SessionLocal, {"writer": writer}, now=lambda: at(0))
    assert _job(db, marker).status == FAILED
    assert db.scalars(select(Job).where(Job.name == "side-effect")).first() is None


def test_scheduled_job_runs_through_worker_cycle(db):
    """Расписание → очередь → обработчик: один оборот воркера."""
    from app.bootstrap.jobs_worker import run_once
    from app.core.manifest import ModuleManifest

    calls: list[int] = []
    from tests.jobs import handlers
    handlers.CALLS = calls
    manifest = ModuleManifest(name="t", title="t", order=1,
                              jobs=(JobSpec("tick_job", "tests.jobs.handlers:record", every_seconds=60),))
    schedule.sync(db, manifest.jobs, now=dt.datetime.now(dt.UTC))
    counts = run_once([manifest])
    assert counts["scheduled"] == 1 and counts["done"] == 1 and calls == [1]
