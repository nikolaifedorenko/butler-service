"""Версия схемы БД — Alembic (ADR-0002, пересмотрен 21.10.2026).

Ревизии лежат в app/bootstrap/alembic/versions; адрес БД и модели — те же, что у
приложения (env.py берёт app.core.db). Новая ревизия:
    alembic revision --autogenerate -m "что меняем"
"""
from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config

# схема main 3801abf (21.10.2026) — сюда штампуются базы, созданные до перехода на Alembic
BASELINE = "0001"


def config() -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", str(Path(__file__).with_name("alembic")))
    return cfg


def upgrade() -> None:
    command.upgrade(config(), "head")


def stamp_baseline() -> None:
    command.stamp(config(), BASELINE)
