"""Проверка DB-02 на живом PostgreSQL: вызываются НАСТОЯЩИЕ функции миграций.

Каждый сценарий: пересоздать схему public → create_all (как init_db) → подготовить условие
(старая колонка, старая запись) → вызвать конкретную функцию migrate_* → записать ошибку.

    PG_URL=postgresql+psycopg2://postgres:pg@127.0.0.1:55432/postgres \
        .venv/bin/python docs/audit/scripts/pg_check.py
"""
from __future__ import annotations

import os
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
os.environ["DATABASE_URL"] = os.environ["PG_URL"]
os.environ.setdefault("SECRET_KEY", "audit-secret-key-0123456789")
os.environ["NIGHT_SYNC_ENABLED"] = "0"
os.environ["DEMO_SEED"] = "1"

from sqlalchemy import text  # noqa: E402

from app.bootstrap import migrations as m  # noqa: E402
from app.bootstrap import registry  # noqa: E402
from app.core.db import Base, engine  # noqa: E402


def fresh() -> None:
    engine.dispose()
    with engine.begin() as con:
        con.execute(text("DROP SCHEMA public CASCADE"))
        con.execute(text("CREATE SCHEMA public"))
    registry.wire()
    Base.metadata.create_all(bind=engine)


def sql(*stmts: str) -> None:
    with engine.begin() as con:
        for s in stmts:
            con.execute(text(s))


def orm_add(make) -> None:
    """Подготовка условий через ORM (Python-defaults колонок заполняются как в приложении)."""
    from types import SimpleNamespace

    from app.core.db import SessionLocal
    from app.modules.night.adapters.orm import NightArea
    from app.modules.timesheet.adapters.orm import ShiftType
    with SessionLocal() as db:
        db.add_all(make(SimpleNamespace(ShiftType=ShiftType, NightArea=NightArea)))
        db.commit()


def first_line(exc: BaseException) -> str:
    msg = str(getattr(exc, "orig", exc)).strip().splitlines()[0]
    return f"{type(getattr(exc, 'orig', exc)).__name__}: {msg}"


def where(exc: BaseException) -> str:
    tb = [f for f in traceback.extract_tb(exc.__traceback__) if "app/bootstrap/migrations.py" in f.filename
          or "app/main.py" in f.filename]
    return ", ".join(f"{Path(f.filename).name}:{f.lineno}" for f in tb[-2:])


SCENARIOS = []


def scenario(title: str):
    def deco(fn):
        SCENARIOS.append((title, fn))
        return fn
    return deco


@scenario("init_db() целиком на ЧИСТОЙ базе")
def s_init():
    with engine.begin() as con:
        con.execute(text("DROP SCHEMA public CASCADE"))
        con.execute(text("CREATE SCHEMA public"))
    engine.dispose()
    from app.main import init_db
    init_db()


@scenario("_migrate_employment_periods() — `e.active = 0` (migrations.py:252-269), каждый старт")
def s_employment():
    fresh()
    m._migrate_employment_periods()


@scenario("migrate_db(): ADD COLUMN punch_in_allowed BOOLEAN DEFAULT 1 (migrations.py:93)")
def s_bool_default_1():
    fresh()
    sql("ALTER TABLE shift_types DROP COLUMN punch_in_allowed")
    m.migrate_db()


@scenario("migrate_db(): ADD COLUMN moved BOOLEAN DEFAULT 0 (migrations.py:128)")
def s_bool_default_0():
    fresh()
    sql("ALTER TABLE car_night_checks DROP COLUMN moved")
    m.migrate_db()


@scenario("migrate_db(): ADD COLUMN dispatched_at DATETIME (migrations.py:122)")
def s_datetime_db():
    fresh()
    sql("ALTER TABLE night_check_items DROP COLUMN dispatched_at")
    m.migrate_db()


@scenario("migrate_night_reopened_at(): ADD COLUMN reopened_at DATETIME (migrations.py:603)")
def s_datetime_reopened():
    fresh()
    sql("ALTER TABLE night_reports DROP COLUMN reopened_at")
    m.migrate_night_reopened_at()


@scenario("migrate_timeoff_entity(): UPDATE shift_types SET active=0 (migrations.py:401), есть AWAY_HOURS")
def s_timeoff():
    fresh()
    orm_add(lambda c: [c.ShiftType(code="TIMEOFF_HOURS", name="Отпросился", kind="absence"),
                       c.ShiftType(code="AWAY_HOURS", name="Отпросился (старый)", kind="absence")])
    m.migrate_timeoff_entity()


@scenario("migrate_night_zones(): INSERT night_zones (…, active=1) (migrations.py:568), область без зоны")
def s_zones():
    fresh()
    orm_add(lambda c: [c.NightArea(name="Холл", category="Корпус A")])
    m.migrate_night_zones()


@scenario("migrate_schedule_dict_simplify(): база с tzh_code и без TIMEOFF_HOURS (migrations.py:750-758)")
def s_dict_simplify():
    fresh()
    sql("ALTER TABLE shift_types ADD COLUMN tzh_code VARCHAR(16) DEFAULT ''")
    m.migrate_schedule_dict_simplify()


def main():
    print(f"# PostgreSQL: {engine.connect().execute(text('select version()')).scalar().split(',')[0]}")
    for title, fn in SCENARIOS:
        try:
            fn()
            print(f"OK   | {title}")
        except Exception as exc:  # noqa: BLE001
            print(f"FAIL | {title} | {first_line(exc)} | {where(exc)}")


if __name__ == "__main__":
    main()
