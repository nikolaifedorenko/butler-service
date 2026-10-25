"""Подключение к БД. По умолчанию SQLite, для продакшена достаточно поменять DATABASE_URL на PostgreSQL."""
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import settings

is_sqlite = settings.database_url.startswith("sqlite")
connect_args = {"check_same_thread": False} if is_sqlite else {}

engine = create_engine(settings.database_url, connect_args=connect_args, future=True)

if is_sqlite:
    @event.listens_for(engine, "connect")
    def _sqlite_pragmas(dbapi_conn, _record):
        """WAL: писатели не блокируют читателей (пересменка, когда все жмут «Пришёл»),
        busy_timeout — ждать разблокировки вместо мгновенной ошибки «database is locked»;
        foreign_keys — проверка внешних ключей, как на PostgreSQL: без неё SQLite молча
        оставлял записи со ссылкой на удалённую строку (рецензия аудита 22.10.2026)."""
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA busy_timeout=10000")
        cur.execute("PRAGMA synchronous=NORMAL")
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)


class Base(DeclarativeBase):
    pass


def lock_employee(db, employee_id: int) -> None:
    """Сериализовать записи входных данных сотрудника (отметки, Табель, График, банк) с
    закрытием и пересчётом его периода — до конца текущей транзакции.

    Закрытие читает вход и пишет результат в одной транзакции, но на PostgreSQL
    (READ COMMITTED) каждый запрос видит свежие коммиты: правка, закоммиченная между
    чтением и сохранением, в закрытый результат не попадала (рецензия аудита 22.10.2026,
    TOCTOU). PostgreSQL — блокировка строки сотрудника; SQLite FOR UPDATE не знает,
    поэтому — пустой UPDATE: он берёт блокировку записи базы до commit.
    """
    if db.get_bind().dialect.name == "sqlite":
        db.execute(text("UPDATE employees SET id = id WHERE id = :id"), {"id": employee_id})
    else:
        db.execute(text("SELECT id FROM employees WHERE id = :id FOR UPDATE"), {"id": employee_id})


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
