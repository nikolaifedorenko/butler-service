"""Замок инициализации схемы БД (P0-2 ревью 20.10.2026).

Зачем
-----
`app.main.init_db()` при КАЖДОМ старте гоняет ~15 шагов DDL/данных, а прод-профиль
запускает несколько воркеров uvicorn (`docker-compose.prod.yml`, UVICORN_WORKERS=2).
Без сериализации два воркера одновременно:

* делают `ALTER TABLE … ADD COLUMN` → «duplicate column name» → воркер падает;
* вызывают `sync_reports(db, force=True)` → IntegrityError по `night_reports.date`
  (unique) — оба создают отчёт за одну и ту же ночь.

Как устроено
------------
Механизм выбирается по типу БД, потому что «лидер-воркер» и файловый лок решают
разные задачи:

* **PostgreSQL** — сеансовый advisory-lock (`pg_try_advisory_lock`): держится на
  соединении, работает и между воркерами, и между контейнерами (горизонтальное
  масштабирование), не оставляет файлов;
* **SQLite и прочие** — `flock` на файле рядом с файлом БД: процессы разные, а файл
  один (для SQLite это единственный общий ресурс). В Windows `fcntl` нет — там лок
  не ставится: это локальный сценарий с одним воркером, гонки нет (пишем в лог).

Замок НЕ «лидер-выборы»: второй воркер просто ждёт первого и затем прогоняет те же
идемпотентные шаги — дёшево (секунды) и без отдельной команды миграций в compose.
Отдельный шаг `python -m app.bootstrap.migrate` до uvicorn и таблица версий шагов
(мост к Alembic, ADR-0002) — осознанно вне этой правки.
"""
from __future__ import annotations

import contextlib
import hashlib
import logging
import tempfile
import time
from collections.abc import Iterator
from pathlib import Path

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
    impl = _pg_lock if engine.url.get_backend_name() == "postgresql" else _file_lock
    with impl(timeout):
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


@contextlib.contextmanager
def _file_lock(timeout: float) -> Iterator[None]:
    """`flock` на файле рядом с БД (SQLite: общий ресурс всех воркеров — файл базы)."""
    try:
        import fcntl
    except ImportError:                       # pragma: no cover — Windows
        log.warning("init_db: файловый замок недоступен (нет fcntl) — старт без сериализации; "
                    "для нескольких воркеров используйте PostgreSQL")
        yield
        return

    path = _lock_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    fh = path.open("a+")                      # не truncate: файл общий
    try:
        deadline = time.monotonic() + timeout
        waited = False
        while True:
            try:
                fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError:
                if time.monotonic() > deadline:
                    raise RuntimeError(
                        f"Не дождался замка инициализации схемы {path} за {timeout:.0f} с"
                        ) from None
                if not waited:
                    log.info("init_db: жду замок инициализации схемы %s (другой воркер)…", path)
                    waited = True
                time.sleep(_POLL_S)
        try:
            yield
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)
    finally:
        fh.close()


def _lock_path() -> Path:
    """Файл замка: рядом с файлом БД, а для не-файловых URL — в tempdir по хешу URL."""
    url = engine.url
    database = url.database or ""
    if url.get_backend_name() == "sqlite" and database and database != ":memory:":
        return Path(database + ".startup.lock")
    digest = hashlib.sha256(str(url).encode()).hexdigest()[:16]
    return Path(tempfile.gettempdir()) / f"butler-startup-{digest}.lock"
