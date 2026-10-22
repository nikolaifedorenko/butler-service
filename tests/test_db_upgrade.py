"""Обновление старых баз и Alembic (аудит 21.10.2026: DB-01, DB-02, переход на Alembic).

Шаги init_db прогоняются на схеме прошлых версий; тесты идут и на SQLite, и на
PostgreSQL (CI-джоб postgres): raw-SQL миграций обязан быть переносимым.
"""
from __future__ import annotations

from sqlalchemy import inspect, select, text


def test_dict_simplify_on_pre_18_10_schema(db):
    """База до 18.10.2026: в shift_types есть tzh_code и устаревший вид отсутствия.
    Раньше шаг падал TypeError (r["id"] у кортежной строки) — старт не поднимался."""
    from app.bootstrap.migrations import migrate_schedule_dict_simplify
    from app.core.db import engine
    from app.modules.timesheet.adapters.orm import ShiftType

    with engine.begin() as con:
        con.execute(text("ALTER TABLE shift_types ADD COLUMN tzh_code VARCHAR(16) DEFAULT ''"))
    db.add(ShiftType(code="OLD_SICK", name="Больничный (старый словарь)", kind="absence"))
    db.commit()

    migrate_schedule_dict_simplify()

    db.expire_all()
    assert db.scalar(select(ShiftType).where(ShiftType.code == "OLD_SICK")) is None
    assert "tzh_code" not in {c["name"] for c in inspect(engine).get_columns("shift_types")}


def _revisions():
    """(текущая ревизия базы, head ревизий)."""
    from alembic.migration import MigrationContext
    from alembic.script import ScriptDirectory

    from app.bootstrap.schema_version import config
    from app.core.db import engine

    with engine.connect() as con:
        current = MigrationContext.configure(con).get_current_revision()
    return current, ScriptDirectory.from_config(config()).get_current_head()


def test_models_match_migrations(db):
    """Модели совпадают со схемой из ревизий: изменение модели без ревизии Alembic
    (alembic revision --autogenerate) роняет этот тест."""
    from alembic import command

    from app.bootstrap.schema_version import config

    current, head = _revisions()
    assert current == head
    command.check(config())


def test_legacy_base_is_stamped_and_upgraded(db):
    """База до перехода на Alembic (нет alembic_version): прежние шаги, штамп baseline,
    затем ревизии до head; повторный старт идёт уже по ревизиям."""
    from app.core.db import engine
    from app.main import init_db

    with engine.begin() as con:
        con.execute(text("DROP TABLE alembic_version"))
    init_db()
    current, head = _revisions()
    assert current == head
    init_db()
    assert _revisions() == (head, head)


def test_cars_holder_index_skipped_when_holder_has_two_cars(db):
    """Ревизия 0004 (CONC-01) на базе, где человек уже держит два кара: данные не трогаем,
    индекс не создаём, старт не падает. После возврата лишнего кара индекс создаётся."""
    from alembic import command

    from app.bootstrap.schema_version import config
    from app.core.db import engine
    from app.core.identity import User
    from app.modules.cars.application.catalog import Car

    def has_index():
        return "ux_cars_holder_user_id" in {i["name"] for i in inspect(engine).get_indexes("cars")}

    cars = db.scalars(select(Car).where(Car.holder_user_id.is_(None)).order_by(Car.id)).all()[:2]
    uid = db.scalar(select(User.id).where(User.id.not_in(
        select(Car.holder_user_id).where(Car.holder_user_id.is_not(None)))))
    db.rollback()       # открытое чтение cars держало бы DROP INDEX на PostgreSQL
    command.downgrade(config(), "0003")
    try:
        for car in cars:
            car.holder_user_id = uid
        db.commit()
        command.upgrade(config(), "head")
        assert not has_index()
    finally:
        for car in cars:
            car.holder_user_id = None
        db.commit()
        command.downgrade(config(), "0003")
        command.upgrade(config(), "head")
    assert has_index()


def test_migrate_command_prepares_empty_base(tmp_path):
    """5.2 (ADR-0002): `python -m app.bootstrap.migrate` — отдельный шаг деплоя — доводит пустую
    базу до head и создаёт администратора из ADMIN_PASSWORD."""
    import os
    import sqlite3
    import subprocess
    import sys
    from pathlib import Path

    db = tmp_path / "migrate.db"
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{db}", "DEMO_SEED": "0",
           "ADMIN_PASSWORD": "admin-pass-123", "NIGHT_SYNC_ENABLED": "0"}
    r = subprocess.run([sys.executable, "-m", "app.bootstrap.migrate"], env=env,
                       cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True,
                       timeout=180)
    assert r.returncode == 0, r.stderr[-2000:]
    _, head = _revisions()
    con = sqlite3.connect(db)
    try:
        assert con.execute("SELECT version_num FROM alembic_version").fetchone()[0] == head
        assert con.execute("SELECT role FROM users WHERE username = 'admin'").fetchone()[0] == "admin"
    finally:
        con.close()


def test_worker_without_migrate_stops_on_stale_schema(db):
    """MIGRATE_ON_START=0: воркер не мигрирует, а при отставании схемы останавливается с
    подсказкой про шаг migrate; на актуальной схеме молчит."""
    import pytest
    from alembic import command

    from app.bootstrap import schema_version

    schema_version.ensure_current()
    db.rollback()
    command.downgrade(schema_version.config(), "-1")
    try:
        with pytest.raises(RuntimeError, match="app.bootstrap.migrate"):
            schema_version.ensure_current()
    finally:
        command.upgrade(schema_version.config(), "head")
