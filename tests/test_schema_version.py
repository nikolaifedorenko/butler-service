"""Версия схемы: ревизии Alembic совпадают с моделями, шаг migrate готовит пустую базу,
воркер без миграций останавливается на неготовой схеме."""
from __future__ import annotations

import datetime as dt
import os
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine, insert, select
from sqlalchemy.exc import IntegrityError

from tests.conftest import rows, run_migrate

ROOT = Path(__file__).resolve().parents[1]


def _head() -> str:
    from alembic.script import ScriptDirectory

    from app.bootstrap.schema_version import config

    return ScriptDirectory.from_config(config()).get_current_head()


def test_models_match_migrations(db):
    """Модели совпадают со схемой из ревизий: изменение модели без ревизии Alembic
    (alembic revision --autogenerate) роняет этот тест."""
    from alembic import command
    from alembic.migration import MigrationContext

    from app.bootstrap.schema_version import config
    from app.core.db import engine

    with engine.connect() as con:
        assert MigrationContext.configure(con).get_current_revision() == _head()
    command.check(config())


def test_migrate_command_prepares_empty_base(fresh_database):
    """`python -m app.bootstrap.migrate` — отдельный шаг деплоя — доводит пустую базу до head,
    вставляет справочные строки и создаёт администратора из ADMIN_PASSWORD."""
    r = run_migrate(fresh_database, ADMIN_PASSWORD="admin-pass-123")
    assert r.returncode == 0, r.stderr[-2000:]
    assert rows(fresh_database, "SELECT version_num FROM alembic_version") == [(_head(),)]
    assert rows(fresh_database, "SELECT role FROM users WHERE username = 'admin'") == [("admin",)]
    roles = {code for (code,) in rows(fresh_database, "SELECT code FROM roles")}
    assert roles == {"admin", "manager", "supervisor", "employee", "mgmt_view", "occupancy"}
    assert rows(fresh_database, "SELECT id FROM stays_settings") == [(1,)]
    assert rows(fresh_database, "SELECT status FROM fund_versions") == [("published",)]


def test_deferred_carry_rejects_exact_duplicate(db):
    """База запрещает хранить один и тот же блок переноса дважды."""
    from app.modules.people.application import Employee
    from app.modules.timesheet.adapters.orm import DeferredCarry

    period = dt.date(2030, 1, 1)          # за пределами демо-периодов: никто не читает
    emp_id = db.scalar(select(Employee.id).limit(1))
    row = DeferredCarry(employee_id=emp_id, period_start=period,
                        source_day=dt.date(2029, 12, 31), tariff="ДЯ", minutes=60)
    db.add(row)
    db.flush()
    db.add(DeferredCarry(employee_id=emp_id, period_start=period,
                         source_day=dt.date(2029, 12, 31), tariff="ДЯ", minutes=60))
    with pytest.raises(IntegrityError) as err:
        db.flush()
    assert err.value.orig.pgcode == "23505"


def test_migrate_preserves_distinct_deferred_carry_blocks(fresh_database):
    """Обновление с 0001 сохраняет разные блоки и удаляет только точные дубли."""
    from app.modules.people.application import Employee
    from app.modules.timesheet.adapters.orm import DeferredCarry

    upgrade = ("from alembic import command; from app.bootstrap.schema_version import config; "
               "command.upgrade(config(), '0001')")
    env = {**os.environ, "DATABASE_URL": fresh_database}
    r = subprocess.run([sys.executable, "-c", upgrade], env=env, cwd=ROOT, capture_output=True,
                       text=True, timeout=120)
    assert r.returncode == 0, r.stderr[-2000:]

    engine = create_engine(fresh_database)
    period_start = dt.date(2030, 1, 1)
    source_day = dt.date(2029, 12, 31)
    try:
        with engine.begin() as con:
            employee_id = con.scalar(insert(Employee.__table__).values(full_name="Deferred carry migration")
                                     .returning(Employee.id))
            carry = dict(employee_id=employee_id, period_start=period_start, source_day=source_day,
                         tariff="ДЯ", minutes=60)
            con.execute(insert(DeferredCarry.__table__), [
                dict(carry, id=3),
                dict(carry, id=1),
                dict(carry, id=2, minutes=120),
            ])
    finally:
        engine.dispose()

    r = run_migrate(fresh_database, ADMIN_PASSWORD="admin-pass-123")
    assert r.returncode == 0, r.stderr[-2000:]
    assert rows(fresh_database, "SELECT id, employee_id, period_start, source_day, tariff, minutes "
                                "FROM deferred_carry ORDER BY id") == [
        (1, employee_id, period_start, source_day, "ДЯ", 60),
        (2, employee_id, period_start, source_day, "ДЯ", 120),
    ]


def test_worker_without_migrate_stops_on_stale_schema(fresh_database):
    """MIGRATE_ON_START=0: воркер не мигрирует, а на неготовой схеме останавливается с
    подсказкой про шаг migrate; после migrate молчит."""
    check = "from app.bootstrap import schema_version; schema_version.ensure_current()"
    env = {**os.environ, "DATABASE_URL": fresh_database}

    r = subprocess.run([sys.executable, "-c", check], env=env, cwd=ROOT, capture_output=True, text=True, timeout=120)
    assert r.returncode != 0 and "app.bootstrap.migrate" in r.stderr, r.stderr[-800:]

    assert run_migrate(fresh_database, ADMIN_PASSWORD="admin-pass-123").returncode == 0
    r = subprocess.run([sys.executable, "-c", check], env=env, cwd=ROOT, capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr[-800:]
