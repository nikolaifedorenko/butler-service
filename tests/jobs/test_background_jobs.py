"""Фоновые дела приложения — задачи очереди (ADR-0013, §6): объявлены в манифестах, обработчики
находятся по именам, поток в приложении больше не запускается."""
from __future__ import annotations

import importlib
import threading

import pytest


def _specs():
    from app.bootstrap import modules

    return {s.name: s for s in modules.job_specs(modules.discover())}


def test_background_work_is_declared_in_manifests(app_stack):
    specs = _specs()
    assert {n: s.every_seconds for n, s in specs.items()} == {
        "night_sync": 60, "notify_outbox": 60, "media_cleanup": 24 * 3600}


def test_every_job_has_a_resolvable_handler(app_stack):
    from app.bootstrap import modules

    handlers = modules.job_handlers(modules.discover())
    assert set(handlers) == set(_specs())
    assert all(callable(h) for h in handlers.values())


def test_outbox_job_marks_interrupted_and_sends_the_queue(app_stack, db, monkeypatch):
    from app.modules.notify.application import jobs

    monkeypatch.setattr(jobs, "fail_stale_sending", lambda s: 2)
    monkeypatch.setattr(jobs, "run_outbox", lambda s: ["a", "b", "c"])
    assert jobs.outbox_job(db, {}) == {"stale": 2, "sent": 3}


def test_night_sync_job_returns_sync_result(app_stack, db, monkeypatch):
    from app.modules.night.application import jobs

    seen = {}
    monkeypatch.setattr(jobs, "sync_reports", lambda s, force: seen.update(force=force) or {"closed": []})
    assert jobs.sync_reports_job(db, {}) == {"closed": []} and seen == {"force": True}


def test_application_no_longer_starts_a_background_thread(app_stack):
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("app.bootstrap.night_sync")
    assert "night-sync" not in {t.name for t in threading.enumerate()}
