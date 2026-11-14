"""Подключение к БД: PostgreSQL (ADR-0013, раздел 3)."""
from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import settings

# pool_pre_ping: соединение, закрытое сервером или сетью, заменяется до запроса, а не падает в нём
engine = create_engine(settings.database_url, pool_pre_ping=True)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def lock_employee(db, employee_id: int) -> None:
    """Сериализовать записи входных данных сотрудника (отметки, Табель, График, банк) с
    закрытием и пересчётом его периода — до конца текущей транзакции.

    Закрытие читает вход и пишет результат в одной транзакции, но на уровне READ COMMITTED
    каждый запрос видит свежие коммиты: правка, закоммиченная между чтением и сохранением,
    в закрытый результат не попадала (TOCTOU). Блокируется строка сотрудника.
    """
    db.execute(text("SELECT id FROM employees WHERE id = :id FOR UPDATE"), {"id": employee_id})


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
