"""Межпроцессные замки: старт приложения и отправка во время запроса.

«Другой воркер» держит замок так же, как настоящий соседний процесс: advisory-lock
PostgreSQL в отдельном соединении.
"""
from __future__ import annotations

import contextlib
import threading
import time

import pytest


@contextlib.contextmanager
def neighbour_holds(name: str | None = None):
    """Замок `name` (None — замок старта) держит соседний процесс."""
    from sqlalchemy import text

    from app.core import startup_lock as sl

    key = sl._LOCK_KEY if name is None else sl._advisory_key(name)
    with sl.engine.connect() as con:
        con.execute(text("SELECT pg_advisory_lock(:k)"), {"k": key})
        con.commit()
        try:
            yield
        finally:
            con.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": key})
            con.commit()


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


def test_lock_keys_are_stable_and_differ_by_name(sl):
    a, b = sl._advisory_key("night-sync"), sl._advisory_key("notify-outbox")
    assert a != b and a == sl._advisory_key("night-sync")
    assert -2**63 <= a < 2**63          # ключ advisory-lock — знаковый int64
