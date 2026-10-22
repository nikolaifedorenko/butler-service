"""Версия схемы БД — Alembic (ADR-0002, пересмотрен 21.10.2026).

Ревизии лежат в app/bootstrap/alembic/versions; адрес БД и модели — те же, что у
приложения (env.py берёт app.core.db). Новая ревизия:
    alembic revision --autogenerate -m "что меняем"
"""
from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config


def config() -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", str(Path(__file__).with_name("alembic")))
    return cfg


def upgrade() -> None:
    command.upgrade(config(), "head")


def ensure_current() -> None:
    """Воркер без MIGRATE_ON_START: схема обязана быть на head, иначе старт останавливается.
    Миграции выполняет отдельный шаг деплоя — python -m app.bootstrap.migrate."""
    from alembic.migration import MigrationContext
    from alembic.script import ScriptDirectory

    from app.core.db import engine

    with engine.connect() as con:
        current = MigrationContext.configure(con).get_current_revision()
    head = ScriptDirectory.from_config(config()).get_current_head()
    if current != head:
        raise RuntimeError(
            f"Схема базы не обновлена (ревизия {current or 'нет'}, нужна {head}): выполните "
            "python -m app.bootstrap.migrate — в прод-профиле это сервис migrate (deploy/README.md §5)")
