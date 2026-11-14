"""Окружение Alembic: та же БД (DATABASE_URL) и те же модели, что у приложения."""
from alembic import context

from app.bootstrap.registry import ensure_models
from app.core.db import Base, engine

ensure_models()

with engine.connect() as connection:
    context.configure(connection=connection, target_metadata=Base.metadata)
    with context.begin_transaction():
        context.run_migrations()
