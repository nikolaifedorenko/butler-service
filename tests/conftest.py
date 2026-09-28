"""Общая настройка тестового прогона.

Зачем этот файл появился
------------------------
Раньше каждый тестовый модуль сам выставлял ``DATABASE_URL`` через
``os.environ.setdefault`` и «заводил» собственный файл БД (tt_test_dicts.db,
tt_doublepay.db, tt_features.db …). На деле настройки читаются один раз
(``functools.lru_cache`` в ``app/config.py``), поэтому все модули работали против
базы, которую определил ПЕРВЫМ импортированный модуль, — файлы-«двойники» не
использовались вовсе. Отсюда и ``tests/test_zz_genitive.py``, названный так, чтобы
импортироваться после ``test_api`` (общая БД), и плавающие результаты при запуске
отдельного файла.

Теперь путь к тестовой БД и SECRET_KEY задаются здесь — до импорта ``app.*`` —
и одинаковы для всего прогона: порядок импорта модулей перестаёт влиять на данные.

Фикстуры
--------
``client`` / ``manager_client`` / ``admin_client`` / ``employee_client``
    TestClient с выполненным входом (демо-пароль ``demo1234``).
``db``
    Сессия SQLAlchemy для прямых проверок состояния.
``sql_counter``
    Подсчёт SQL-запросов — для тестов-стражей от регрессий N+1.
``freeze``
    Фиксация времени (freezegun): тесты границы полуночи и ночной смены.
"""
from __future__ import annotations

import os
import pathlib
import tempfile
from contextlib import contextmanager

import pytest

# ── окружение задаётся ДО импорта app.* ────────────────────────────────────────
TEST_DB = pathlib.Path(tempfile.gettempdir()) / "tt_test.db"
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB}"
os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("APP_TZ", "Europe/Moscow")

DEMO_PASSWORD = "demo1234"


def _drop_db() -> None:
    for suffix in ("", "-wal", "-shm"):
        p = pathlib.Path(str(TEST_DB) + suffix)
        if p.exists():
            p.unlink()


# свежая база на каждый прогон: сид создаётся при первом init_db()
_drop_db()

from fastapi.testclient import TestClient  # noqa: E402

from app.db import SessionLocal  # noqa: E402
from app.main import app, init_db  # noqa: E402

init_db()


@pytest.fixture(scope="session")
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture()
def client() -> TestClient:
    """Неаутентифицированный клиент (проверка прав доступа)."""
    return TestClient(app)


def _login(username: str) -> TestClient:
    c = TestClient(app)
    r = c.post("/api/auth/login", json={"username": username, "password": DEMO_PASSWORD})
    assert r.status_code == 200, f"не удалось войти как {username}: {r.text}"
    return c


@pytest.fixture()
def manager_client() -> TestClient:
    """Старший батлер (supervisor): менеджерские разделы, но не админские."""
    return _login("gromova")


@pytest.fixture()
def admin_client() -> TestClient:
    return _login("admin")


@pytest.fixture()
def employee_client() -> TestClient:
    return _login("ivanov")


@pytest.fixture()
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@contextmanager
def _counting():
    """Контекст: сколько SQL-операторов выполнено (см. fixture sql_counter)."""
    from sqlalchemy import event

    from app.db import engine

    state = {"total": 0, "select": 0, "by_statement": {}}

    def before(conn, cur, stmt, params, ctx, many):
        kind = stmt.strip().split()[0].upper()
        state["total"] += 1
        if kind == "SELECT":
            state["select"] += 1
        key = " ".join(stmt.split())[:60]
        state["by_statement"][key] = state["by_statement"].get(key, 0) + 1

    event.listen(engine, "before_cursor_execute", before)
    try:
        yield state
    finally:
        event.remove(engine, "before_cursor_execute", before)


@pytest.fixture()
def sql_counter():
    """with sql_counter() as c: … → c['total'], c['select'], c['by_statement']."""
    return _counting


@pytest.fixture()
def freeze():
    """Фиксация времени. Время указывается в UTC; APP_TZ=Europe/Moscow (+3).

    Пример: freeze("2026-09-27 23:00:00") → в объекте 02:00 28.09.
    """
    from freezegun import freeze_time

    @contextmanager
    def _freeze(utc_iso: str):
        with freeze_time(utc_iso) as f:
            yield f

    return _freeze
