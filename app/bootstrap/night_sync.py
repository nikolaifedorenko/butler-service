"""Фоновая синхронизация ночных отчётов (ревью 20.10.2026, P1).

Раньше `sync_reports()` (досоздать наступившие смены + автозакрыть прошедшие
дедлайн 08:00) выполнялся прямо в GET /api/night/today и GET /api/night/reports.
Последствия, которые закрыла эта правка:

* GET с побочными записями — неидемпотентность и гонки при параллельном поллинге
  несколькими клиентами;
* ручное переоткрытие отчёта «жило» меньше двух минут: ближайший же GET снова
  запускал sync_reports, и тот закрывал отчёт по прошедшему дедлайну
  (правки падали в 409 «Смена закрыта»).

Теперь GET-запросы раздела читают базу без записей, а обслуживание выполняется:

* при старте сервера — `init_db()` под замком `startup_lock` (app/main.py);
* фоновым потоком с периодом `settings.night_sync_seconds` (по умолчанию 60 с) —
  этот модуль; поток запускает lifespan приложения и только в реальном сервере
  (тестовый TestClient lifespan не запускает и поток не создаёт).

Несколько воркеров uvicorn (docker-compose.prod.yml): поток есть в каждом, но
раунд синхронизации выполняет только один процесс — под неблокирующим замком
`core.startup_lock.try_lock("night-sync")` (PostgreSQL — сеансовый advisory-lock,
SQLite — flock на файле рядом с БД); остальные воркеры раунд пропускают. Это же
убирает гонку создания отчёта (IntegrityError по night_reports.date unique).

Вручную переоткрытые отчёты sync_reports не закрывает (reopened_at) — см.
app/modules/night/application/night.py.
"""
from __future__ import annotations

import logging
import threading

log = logging.getLogger("uvicorn.error")

LOCK_NAME = "night-sync"
MIN_PERIOD_SECONDS = 5          # защита от опечатки в NIGHT_SYNC_SECONDS=1

_thread: threading.Thread | None = None
_stop = threading.Event()


def run_sync_once() -> dict:
    """Один раунд фоновой синхронизации: замок лидера + своя сессия БД.

    Возвращает результат sync_reports() или {"skipped": …}, если раунд уже
    выполняет другой процесс. Исключения не глотает — логгирует вызывающий.
    """
    from ..core.db import SessionLocal
    from ..core.startup_lock import try_lock
    from ..modules.night.application.night import sync_reports

    with try_lock(LOCK_NAME) as got:
        if not got:
            return {"skipped": "раунд выполняет другой процесс"}
        db = SessionLocal()
        try:
            return sync_reports(db, force=True)
        finally:
            db.close()


def _loop(period: float) -> None:
    while not _stop.wait(period):
        try:
            run_sync_once()
        except Exception:                       # раунд не должен ронять поток
            log.exception("night_sync: раунд фоновой синхронизации завершился ошибкой")


def start_night_sync() -> None:
    """Запустить фоновый поток (идемпотентно). Вызывается из lifespan (app/main.py)."""
    global _thread
    from ..core.config import settings

    if not settings.night_sync_enabled:
        log.info("night_sync: фоновая синхронизация отключена (NIGHT_SYNC_ENABLED=0)")
        return
    if _thread is not None and _thread.is_alive():
        return
    period = max(MIN_PERIOD_SECONDS, int(settings.night_sync_seconds))
    _stop.clear()
    _thread = threading.Thread(target=_loop, args=(period,), name=LOCK_NAME, daemon=True)
    _thread.start()
    log.info("night_sync: фоновая синхронизация ночных отчётов каждые %d с", period)


def stop_night_sync() -> None:
    """Остановить фоновый поток (lifespan shutdown; поток daemon и переживёт процесс)."""
    _stop.set()
