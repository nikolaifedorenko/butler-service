"""Окружение Alembic: та же БД (DATABASE_URL) и те же модели, что у приложения."""
from alembic import context

from app.bootstrap.registry import ensure_models
from app.core.db import Base, engine

ensure_models()

with engine.connect() as connection:
    sqlite = connection.dialect.name == "sqlite"
    if sqlite:
        # batch пересоздаёт таблицы через DROP TABLE; с включёнными внешними ключами это падает,
        # если на таблицу уже ссылаются строки. PRAGMA действует только вне транзакции — до неё
        connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
        connection.commit()      # закрыть автотранзакцию SQLAlchemy: иначе Alembic не зафиксирует ревизии
    # SQLite не умеет ALTER COLUMN — batch пересоздаёт таблицу
    context.configure(connection=connection, target_metadata=Base.metadata,
                      render_as_batch=connection.dialect.name == "sqlite")
    with context.begin_transaction():
        context.run_migrations()
    if sqlite:
        broken = connection.exec_driver_sql("PRAGMA foreign_key_check").fetchall()
        connection.commit()      # PRAGMA foreign_keys снова включается только вне транзакции
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")
        connection.commit()
        if broken:
            raise RuntimeError(f"после миграций нарушены внешние ключи: {broken[:5]}")
