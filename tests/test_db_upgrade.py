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
