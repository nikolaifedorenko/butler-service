"""Межпроцессные замки и фоновый поток (аудит, шаг 6.3, ARCH-03).

«Другой воркер» держит замок так же, как настоящий соседний процесс: на PostgreSQL —
advisory-lock в отдельном соединении, на SQLite — flock через отдельный дескриптор файла.
Поэтому один и тот же тест проверяет обе ветки `core/startup_lock.py`: на SQLite в обычном
прогоне и на PostgreSQL в CI-джобе postgres.
"""
from __future__ import annotations

import contextlib
import threading
import time
import types

import pytest


@contextlib.contextmanager
def neighbour_holds(name: str | None = None):
    """Замок `name` (None — замок старта) держит соседний процесс."""
    from sqlalchemy import text

    from app.core import startup_lock as sl

    if sl.engine.url.get_backend_name() == "postgresql":
        key = sl._LOCK_KEY if name is None else sl._advisory_key(name)
        with sl.engine.connect() as con:
            con.execute(text("SELECT pg_advisory_lock(:k)"), {"k": key})
            con.commit()
            try:
                yield
            finally:
                con.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": key})
                con.commit()
        return
    import fcntl

    path = sl._lock_path() if name is None else sl._lock_path_for(name)
    with path.open("a+") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)


@pytest.fixture()
def sl(app_stack):
    from app.core import startup_lock

    assert startup_lock._depth == 0, "тест должен начинаться вне замка старта"
    return startup_lock


def test_startup_lock_fails_loudly_when_neighbour_holds_too_long(sl):
    with neighbour_holds(), pytest.raises(RuntimeError, match="Не дождался замка"), sl.startup_lock(timeout=0.3):
        pytest.fail("замок взят, хотя его держит сосед")
    assert sl._depth == 0


def test_startup_lock_waits_for_neighbour(sl):
    held, release = threading.Event(), threading.Event()

    def neighbour():
        with neighbour_holds():
            held.set()
            release.wait(5)

    t = threading.Thread(target=neighbour)
    t.start()
    held.wait(5)
    threading.Timer(0.5, release.set).start()
    t0 = time.monotonic()
    with sl.startup_lock(timeout=10):
        waited = time.monotonic() - t0
    t.join(5)
    assert waited >= 0.4, "замок взят, пока его держал сосед"


def test_nested_startup_lock_does_not_wait_for_itself(sl):
    with sl.startup_lock(timeout=1), sl.startup_lock(timeout=0.01):     # не no-op — ждал бы сам себя и упал
        assert sl._depth == 2
    assert sl._depth == 0


def test_try_lock_skips_round_while_neighbour_holds(sl):
    with neighbour_holds("probe-job"), sl.try_lock("probe-job") as got:
        assert got is False
    with sl.try_lock("probe-job") as got:
        assert got is True
        with sl.try_lock("probe-job") as again:  # второй «воркер» в тот же момент
            assert again is False


def test_lock_file_for_non_file_database_is_stable_per_url(sl, monkeypatch, tmp_path):
    from sqlalchemy.engine import make_url

    monkeypatch.setattr(sl, "engine", types.SimpleNamespace(url=make_url("postgresql://u@db-1/tt")))
    a, b = sl._lock_path_for("startup"), sl._lock_path_for("night-sync")
    assert a.name.startswith("butler-startup-") and a != b and a == sl._lock_path_for("startup")
    monkeypatch.setattr(sl, "engine", types.SimpleNamespace(url=make_url("postgresql://u@db-2/tt")))
    assert sl._lock_path_for("startup") != a          # разные базы — разные замки


# ── фоновый поток bootstrap/night_sync.py ──────────────────────────────────────

@pytest.fixture()
def ns(app_stack, monkeypatch):
    from app.bootstrap import night_sync

    monkeypatch.setattr(night_sync, "_thread", None)
    monkeypatch.setitem(night_sync._last_cleanup, "ts", None)
    return night_sync


def test_outbox_round_runs_in_one_process(ns, monkeypatch):
    from app.modules.notify.application import dispatch

    monkeypatch.setattr(dispatch, "fail_stale_sending", lambda db: 1)
    monkeypatch.setattr(dispatch, "run_outbox", lambda db: ["a", "b"])
    with neighbour_holds("notify-outbox"):
        assert ns.run_outbox_once() is None              # раунд у соседа
    assert ns.run_outbox_once() == 2


def test_media_cleanup_skipped_while_neighbour_cleans(ns):
    with neighbour_holds("media-cleanup"):
        assert ns.run_media_cleanup_if_due() is None
    assert ns._last_cleanup["ts"] is None                 # чистки не было — попробуем снова


def test_loop_survives_failing_round(ns, monkeypatch):
    calls = []
    monkeypatch.setattr(ns, "run_sync_once", lambda: (calls.append("sync"), 1 / 0))
    monkeypatch.setattr(ns, "run_media_cleanup_if_due", lambda: calls.append("media") or 1 / 0)
    monkeypatch.setattr(ns, "run_outbox_once", lambda: calls.append("outbox"))
    ticks = iter([False, False, True])                    # два раунда, затем стоп
    monkeypatch.setattr(ns, "_stop", types.SimpleNamespace(wait=lambda period: next(ticks)))
    ns._loop(0)
    assert calls == ["sync", "media", "outbox"] * 2


def test_start_is_idempotent_clamps_period_and_respects_flag(ns, monkeypatch):
    from app.core.config import settings

    periods = []

    def fake_loop(period):
        periods.append(period)
        ns._stop.wait(5)

    monkeypatch.setattr(ns, "_loop", fake_loop)
    monkeypatch.setattr(settings, "night_sync_enabled", False)
    ns.start_night_sync()
    assert ns._thread is None
    monkeypatch.setattr(settings, "night_sync_enabled", True)
    monkeypatch.setattr(settings, "night_sync_seconds", 1)     # опечатка: раз в секунду
    try:
        ns.start_night_sync()
        first = ns._thread
        ns.start_night_sync()                              # второй вызов lifespan
        assert ns._thread is first and first.is_alive()
        assert ns._last_cleanup["ts"] is not None          # init_db только что чистил медиа
    finally:
        ns.stop_night_sync()
        ns._thread.join(5)
    assert periods == [ns.MIN_PERIOD_SECONDS] and not first.is_alive()
