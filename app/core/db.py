"""Подключение к БД: PostgreSQL (ADR-0013, раздел 3)."""
import json
from typing import Any

from sqlalchemy import create_engine, event, text
from sqlalchemy.dialects.postgresql import JSON, JSONB
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy.types import TypeDecorator

from .config import settings

# pool_pre_ping: соединение, закрытое сервером или сетью, заменяется до запроса, а не падает в нём
engine = create_engine(settings.database_url, pool_pre_ping=True)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class Json(TypeDecorator):
    """Колонка ``JSONB``: в коде — словарь или список, в базе — разобранный JSON.

    Присвоенное значение записывается всегда, даже если это тот же объект: значение можно
    изменить на месте и присвоить обратно. Изменение на месте без присваивания не
    сохраняется. Порядок ключей словаря база не хранит — где порядок важен, нужен список.
    """

    impl = JSONB
    cache_ok = True

    def compare_values(self, x: Any, y: Any) -> bool:
        return False


class OrderedJson(Json):
    """Колонка ``JSON``: документ, который читается и пишется целиком и хранит порядок ключей.

    Только для документов, где порядок ключей — порядок показа; искать по содержимому
    такой колонки нельзя. Всё остальное — ``Json``.
    """

    impl = JSON
    cache_ok = True


@event.listens_for(Base, "init", propagate=True)
def _fill_json_defaults(target: Any, args: tuple, kwargs: dict) -> None:
    """Новый объект получает пустые значения колонок ``Json`` сразу, а не при записи в базу."""
    for column in target.__table__.columns:
        if isinstance(column.type, Json) and column.default is not None and column.key not in kwargs:
            kwargs[column.key] = column.default.arg(None)


def plain_json(value: Any) -> Any:
    """Значение из одних типов JSON: даты и прочее становятся строками. Возвращает копию."""
    return json.loads(json.dumps(value, default=str))


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
