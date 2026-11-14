"""Замки PostgreSQL для инициализации схемы и фоновых задач.

Прод-профиль запускает несколько воркеров uvicorn и может запускать несколько контейнеров
приложения. Без сериализации два процесса одновременно выполняют миграции и стартовые шаги
(«duplicate column», IntegrityError по уникальным полям) — поэтому:

* ``startup_lock()`` — блокирующий замок инициализации: второй процесс ждёт первого и затем
  повторяет те же идемпотентные шаги;
* ``try_lock(name)`` — неблокирующий именованный замок фоновых задач: раунд работы выполняет
  один процесс, остальные сразу получают False и пропускают раунд.

Оба — сеансовые advisory-lock (``pg_try_advisory_lock``): держатся на соединении, работают
между воркерами и контейнерами, файлов не оставляют.
"""
from __future__ import annotations

import contextlib
import hashlib
import logging
import time
from collections.abc import Iterator

from .db import engine

log = logging.getLogger("uvicorn.error")

# произвольная, но стабильная константа: один ключ на «инициализацию схемы»
_LOCK_KEY = 0x62746C72_73746172         # "btlrstar" в int8
_TIMEOUT_S = 300.0                      # ждём лидера; дальше — громкий отказ старта
_POLL_S = 0.2
_depth = 0                              # вложенные вызовы в том же процессе — no-op


@contextlib.contextmanager
def startup_lock(timeout: float = _TIMEOUT_S) -> Iterator[None]:
    """Сериализация инициализации схемы между воркерами/процессами.

    Вложенный вызов в том же процессе замок не берёт (init_db идемпотентна, но
    ждать саму себя смысла нет). При превышении `timeout` бросает RuntimeError:
    старт должен упасть громко и перезапуститься, а не молча гонять DDL в гонке.
    """
    global _depth
    if _depth:
        _depth += 1
        try:
            yield
        finally:
            _depth -= 1
        return
    with _pg_lock(timeout):
        _depth = 1
        try:
            yield
        finally:
            _depth = 0


@contextlib.contextmanager
def _pg_lock(timeout: float) -> Iterator[None]:
    """Сеансовый advisory-lock PostgreSQL: живёт до unlock или до конца соединения."""
    from sqlalchemy import text

    with engine.connect() as con:
        deadline = time.monotonic() + timeout
        waited = False
        while not con.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": _LOCK_KEY}).scalar():
            if time.monotonic() > deadline:
                raise RuntimeError(
                    f"Не дождался замка инициализации схемы (pg_advisory_lock {_LOCK_KEY}) "
                    f"за {timeout:.0f} с — другой процесс держит его слишком долго")
            if not waited:
                log.info("init_db: жду замок инициализации схемы (другой воркер)…")
                waited = True
            time.sleep(_POLL_S)
        con.commit()          # advisory-lock сеансовый — транзакцию не держим открытой
        try:
            yield
        finally:
            con.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": _LOCK_KEY})
            con.commit()


# ─────────────────── неблокирующий замок фоновых задач ───────────────────

def _advisory_key(name: str) -> int:
    """Стабильный int64-ключ advisory-lock по имени замка."""
    digest = hashlib.sha256(name.encode()).digest()
    return int.from_bytes(digest[:8], "big", signed=True)


@contextlib.contextmanager
def try_lock(name: str) -> Iterator[bool]:
    """Неблокирующий межпроцессный замок: True — взяли, False — держит сосед.

    Для фоновых задач в нескольких воркерах и контейнерах: раунд работы выполняет тот, кто
    успел взять замок, остальные пропускают раунд без ожидания. Ключ — хеш имени.
    """
    from sqlalchemy import text

    key = _advisory_key(name)
    with engine.connect() as con:
        got = bool(con.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": key}).scalar())
        con.commit()        # advisory-lock сеансовый — транзакцию открытой не держим
        try:
            yield got
        finally:
            if got:
                con.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": key})
                con.commit()
