"""Общая настройка тестового прогона.

База — PostgreSQL (ADR-0013, раздел 3). Сервер поднимает `docker compose up -d db`; адрес
без имени базы задаёт TEST_DATABASE_SERVER (по умолчанию — локальный из docker-compose.yml).
У каждого потока pytest-xdist своя база `butler_test_<поток>`: она пересоздаётся в начале
прогона и заполняется демо-данными при первом init_db(). Тесты одного файла идут в одном
потоке по порядку (`--dist loadfile` в pyproject.toml).

Окружение задаётся здесь — до импорта ``app.*``: настройки читаются один раз.

Фикстуры
--------
``client`` / ``manager_client`` / ``admin_client`` / ``employee_client``
    TestClient с выполненным входом (демо-пароль ``demo1234``).
``db``
    Сессия SQLAlchemy для прямых проверок состояния.
``fresh_database``
    Адрес новой пустой базы — для тестов, которые запускают приложение отдельным процессом.
``sql_counter``
    Подсчёт SQL-запросов — для тестов-стражей от регрессий N+1.
``freeze``
    Фиксация времени (freezegun): тесты границы полуночи и ночной смены.
"""
from __future__ import annotations

import os
import uuid
from contextlib import contextmanager

import pytest
from sqlalchemy import create_engine, text

# ── окружение задаётся ДО импорта app.* ────────────────────────────────────────
TEST_SERVER = os.environ.get("TEST_DATABASE_SERVER", "postgresql+psycopg2://postgres:dev@127.0.0.1:54329")
WORKER = os.environ.get("PYTEST_XDIST_WORKER", "main")


def _admin():
    """Соединение с сервером вне транзакции: CREATE и DROP DATABASE в транзакции нельзя."""
    return create_engine(f"{TEST_SERVER}/postgres", isolation_level="AUTOCOMMIT")


def create_database(name: str) -> str:
    """Пересоздать пустую базу и вернуть её адрес."""
    admin = _admin()
    try:
        with admin.connect() as con:
            con.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
            con.execute(text(f'CREATE DATABASE "{name}"'))
    except Exception as exc:
        raise RuntimeError(
            f"Тестам нужен PostgreSQL по адресу {TEST_SERVER}: запустите `docker compose up -d db` "
            f"или задайте TEST_DATABASE_SERVER ({type(exc).__name__})") from exc
    finally:
        admin.dispose()
    return f"{TEST_SERVER}/{name}"


def drop_database(name: str) -> None:
    admin = _admin()
    with admin.connect() as con:
        con.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
    admin.dispose()


# свежая база на каждый прогон: сид создаётся при первом init_db()
os.environ["DATABASE_URL"] = create_database(f"butler_test_{WORKER}")
os.environ.setdefault("SECRET_KEY", "test-secret-key")
# тесты опираются на демо-сотрудников и пароль demo1234 (см. app/bootstrap/seed.py)
os.environ.setdefault("DEMO_SEED", "1")
os.environ.setdefault("APP_TZ", "Europe/Moscow")
# CSRF-защита — браузерный механизм (cookie + заголовок); TestClient её не имитирует,
# поэтому в тестах отключаем. Сам механизм покрыт отдельно (см. tests/test_csrf.py).
os.environ.setdefault("CSRF_ENABLED", "0")
# демо-вход «как сотрудник» включён по умолчанию (решение владельца 15.10.2026);
# в тестах фиксируем явно, чтобы прогон не зависел от внешнего окружения
# (тесты test_13_impersonation / test_impersonated_manager проверяют механизм).
os.environ.setdefault("ALLOW_IMPERSONATION", "1")
# секреты уведомлений в БД шифруются (app/modules/notify/application/secrets.py): тесты
# сохраняют токен бота и пароль SMTP — нужен ключ. Только для тестов.
os.environ.setdefault("NOTIFY_SECRET_KEY", "qX4m2HcV8sRw0yE1nK6tPzL9bJ3uA7dF5gTiOoMlYe0=")

DEMO_PASSWORD = "demo1234"


def run_migrate(url: str, **env: str):
    """Шаг деплоя `python -m app.bootstrap.migrate` отдельным процессом на базе url."""
    import subprocess
    import sys
    from pathlib import Path

    full = {**os.environ, "DATABASE_URL": url, "DEMO_SEED": "0", "NIGHT_SYNC_ENABLED": "0", **env}
    return subprocess.run([sys.executable, "-m", "app.bootstrap.migrate"], env=full,
                          cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True, timeout=300)


def rows(url: str, sql: str) -> list:
    """Строки запроса к базе url."""
    eng = create_engine(url)
    try:
        with eng.connect() as con:
            return [tuple(r) for r in con.execute(text(sql))]
    finally:
        eng.dispose()


@pytest.fixture()
def fresh_database():
    """Адрес новой пустой базы; после теста база удаляется."""
    name = f"butler_tmp_{uuid.uuid4().hex[:12]}"
    try:
        yield create_database(name)
    finally:
        drop_database(name)


@pytest.fixture(scope="session")
def app_stack():
    """Ленивая инициализация приложения.

    Приёмочные тесты движка (tests/engine/) проверяют чистый домен и не должны
    поднимать FastAPI/БД; до импорта `app.main` дело доходит только здесь.
    """
    from fastapi.testclient import TestClient  # noqa: F401

    from app.core.db import SessionLocal
    from app.main import app, init_db

    init_db()
    # FastAPI строит pydantic-схемы маршрутов ЛЕНИВО (при первом матчинге запроса).
    # Если первая сборка попадает внутрь freeze_time, аннотация dt.date подменена на
    # FakeDate и построение падает (см. tests/test_tz_local_date.py) — тесты становятся
    # зависимыми от порядка запуска. Прогрев всех маршрутов на старте сессии (вне
    # любой заморозки) делает порядок безразличным: app.openapi() обращается к
    # dependant каждого маршрута и кэширует схемы.
    app.openapi()
    return {"app": app, "SessionLocal": SessionLocal}


@pytest.fixture(scope="session")
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture()
def client(app_stack):
    """Неаутентифицированный клиент (проверка прав доступа)."""
    from fastapi.testclient import TestClient

    return TestClient(app_stack["app"])


def _login(app, username: str):
    from fastapi.testclient import TestClient

    c = TestClient(app)
    r = c.post("/api/auth/login", json={"username": username, "password": DEMO_PASSWORD})
    assert r.status_code == 200, f"не удалось войти как {username}: {r.text}"
    return c


@pytest.fixture()
def manager_client(app_stack):
    """Старший батлер (supervisor): менеджерские разделы, но не админские."""
    return _login(app_stack["app"], "gromova")


@pytest.fixture()
def manager_role_client(app_stack):
    """Менеджер объекта (роль manager): права cars.manage в отличие от supervisor."""
    return _login(app_stack["app"], "smirnov")


@pytest.fixture()
def admin_client(app_stack):
    return _login(app_stack["app"], "admin")


@pytest.fixture()
def employee_client(app_stack):
    return _login(app_stack["app"], "ivanov")


@pytest.fixture()
def db(app_stack):
    session = app_stack["SessionLocal"]()
    try:
        yield session
    finally:
        session.close()


@contextmanager
def _counting():
    """Контекст: сколько SQL-операторов выполнено (см. fixture sql_counter)."""
    from sqlalchemy import event

    from app.core.db import engine

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
def freeze(monkeypatch):
    """Фиксация времени. Время указывается в UTC; APP_TZ=Europe/Moscow (+3).

    Пример: freeze("2026-09-27 23:00:00") → в объекте 02:00 28.09.

    Срок жизни сессии на время заморозки — 20 лет. Обработчики запросов идут в рабочих
    потоках, а freezegun в них (стек с threading) отдаёт настоящее время: токен, выданный
    на замороженную дату, через 48 часов реального времени считался бы просроченным, и тест
    начинал падать с 401 в день, зависящий от календаря (ноябрь 2026: month_boundary).
    """
    from freezegun import freeze_time

    from app.core.config import settings

    @contextmanager
    def _freeze(utc_iso: str):
        with monkeypatch.context() as m:
            m.setattr(settings, "session_ttl_hours", 24 * 365 * 20)
            with freeze_time(utc_iso) as f:
                yield f

    return _freeze


@pytest.fixture()
def open_shift(db, freeze):
    """with open_shift() as rep: … → открытый отчёт ночной смены + уборка за тестом.

    Отчёт берём за СЕГОДНЯШНЮЮ дату и создаём под заморозкой времени (23:00 UTC —
    середина смены), а HTTP-запросы тест выполняет уже БЕЗ freeze: FastAPI
    достраивает pydantic-схемы маршрутов лениво, и внутри freeze_time аннотация
    ``dt.date`` подменена на ``FakeDate`` — схема не строится. Автозакрытие
    сегодняшней смены (08:00 следующих суток) ещё не наступило, поэтому
    ``sync_reports`` отчёт не закроет и загрузка отметок остаётся разрешённой.

    Если отчёт за сегодня уже создан другим тестом, мы его не удаляем — только
    возвращаем прежний статус и убираем файлы, загруженные этим тестом.

    ГЕРМЕТИЧНОСТЬ (19.10.2026): когда прогон идёт во время НАСТОЯЩЕЙ ночной смены
    (после 20:00 времени объекта), ``sync_reports(force=True)`` при старте
    приложения создаёт отчёт за сегодня РАНЬШЕ первого open_shift — фикстура
    переиспользует его (created=False) и не удаляет в teardown, поэтому отметки,
    отправки и закрытые объекты предыдущих тестов протекали в следующие
    (dispatch находил «всё уже отправлено», выборочная отправка получала 422 на
    пустом списке). Днём отчёт создаёт сама фикстура и удаляет его — сброс просто
    no-op. Перед yield отчёт приводится к состоянию «смена началась, никто ничего
    не отмечал»: секции свободны, ответы и отправки сняты, перехваты и ночные
    отметки каров удалены. Все потребители сегодняшнего отчёта
    (media_video, dispatch, export_v2, services) размечают свои пункты сами.
    """
    import datetime as dt
    from contextlib import contextmanager as _cm

    from sqlalchemy import select

    from app.core.media import Photo, unlink_photo
    from app.modules.cars.application.catalog import CarNightCheck
    from app.modules.night.application.catalog import (
        NightAreaSection,
        NightCheckItem,
        NightInterception,
        NightReport,
    )
    from app.modules.night.application.night import ensure_report

    @_cm
    def _open():
        shift_d = dt.date.today()
        existed = db.scalar(select(NightReport).where(NightReport.date == shift_d))
        prev_state = ((existed.status, existed.closed_at, existed.close_reason,
                       existed.reopened_at) if existed else None)
        with freeze(f"{shift_d.isoformat()} 23:00:00"):
            rep = ensure_report(db, shift_d)
        assert rep is not None, "отчёт смены не создан"
        created = existed is None
        rep.status, rep.closed_at = "open", None        # тесту нужен открытый отчёт
        rep.close_reason, rep.result, rep.cars_step_done = "", "", False
        rep.reopened_at = None     # «чистая смена»: автозакрытие не выключено
        # сброс к «чистой смене» — см. докстринг (герметичность при прогоне ночью)
        secs = list(db.scalars(select(NightAreaSection)
                               .where(NightAreaSection.report_id == rep.id)))
        for sec in secs:
            sec.taken_by, sec.taken_by_name, sec.taken_at = None, "", None
            sec.status, sec.closed_at, sec.closed_by = "free", None, None
        sec_ids = [s.id for s in secs]
        if sec_ids:
            items = list(db.scalars(select(NightCheckItem)
                                    .where(NightCheckItem.section_id.in_(sec_ids))))
            for p in db.scalars(select(Photo).where(
                    Photo.kind == "night_item",
                    Photo.ref_id.in_([i.id for i in items] or [0]))):
                unlink_photo(p)
                db.delete(p)
            for it in items:
                it.answer, it.comment = "", ""
                it.answered_by, it.answered_by_name, it.answered_at = None, "", None
                it.dispatch_id, it.dispatched_at = None, None
        for row in db.scalars(select(NightInterception)
                              .where(NightInterception.report_id == rep.id)):
            db.delete(row)
        for row in db.scalars(select(CarNightCheck)
                              .where(CarNightCheck.report_id == rep.id)):
            db.delete(row)
        db.commit()
        start = dt.datetime.now() - dt.timedelta(seconds=1)
        try:
            yield rep
        finally:
            sec_ids = [s.id for s in db.scalars(
                select(NightAreaSection).where(NightAreaSection.report_id == rep.id))]
            item_ids = ([i.id for i in db.scalars(select(NightCheckItem).where(
                NightCheckItem.section_id.in_(sec_ids)))] if sec_ids else [])
            for p in db.scalars(select(Photo).where(Photo.kind == "night_item",
                                                    Photo.ref_id.in_(item_ids))):
                if created or (p.created_at and p.created_at >= start):
                    unlink_photo(p)
                    db.delete(p)
            db.flush()
            if created:
                for i in db.scalars(select(NightCheckItem)
                                    .where(NightCheckItem.section_id.in_(sec_ids))):
                    db.delete(i)
                db.flush()
                for s in db.scalars(select(NightAreaSection)
                                    .where(NightAreaSection.report_id == rep.id)):
                    db.delete(s)
                db.flush()
                fresh = db.get(NightReport, rep.id)
                if fresh is not None:
                    db.delete(fresh)
            else:
                (rep.status, rep.closed_at, rep.close_reason,
                 rep.reopened_at) = prev_state
            db.flush()
            db.commit()

    return _open
