"""Отдельный шаг деплоя: миграции схемы, справочники движка, сид и первый администратор.

    python -m app.bootstrap.migrate

В прод-профиле его выполняет сервис `migrate` docker-compose до старта приложения, а воркеры
с MIGRATE_ON_START=0 только сверяют ревизию схемы (ADR-0002, аудит 22.10.2026, DB-02, SEC-02).
Локально и в демо-compose всё по-прежнему делает первый воркер при старте.
"""
from __future__ import annotations

import logging


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    from app.main import init_db

    init_db()
    logging.getLogger("uvicorn.error").info("migrate: схема и справочники готовы")


if __name__ == "__main__":
    main()
