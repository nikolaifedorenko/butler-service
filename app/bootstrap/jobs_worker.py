"""Воркер очереди задач: отдельный процесс ``python -m app.bootstrap.jobs_worker`` (ADR-0013, §6).

Приложение (uvicorn) задач не выполняет: так фоновая работа не делит процесс с запросами, её можно
перезапускать и масштабировать отдельно. Воркер:

* подключает модули и проверяет, что схема базы актуальна (миграции делает сервис ``migrate``);
* приводит расписание к списку задач из манифестов (``jobs=(JobSpec(...),)``);
* в цикле: ставит в очередь наступившие расписания, возвращает зависшие задачи, выполняет готовые;
* по SIGTERM/SIGINT доделывает текущую задачу и выходит.

Несколько воркеров безопасны: задачи берутся ``FOR UPDATE SKIP LOCKED``, расписание тикает один раз.
"""
from __future__ import annotations

import logging
import signal
import threading

log = logging.getLogger("uvicorn.error")


def run_once(manifests, *, limit: int = 100) -> dict:
    """Один оборот цикла: расписание → зависшие → готовые задачи. Возвращает счётчики."""
    from app.core.config import settings
    from app.core.db import SessionLocal
    from app.modules.jobs.application import queue, runner, schedule

    from . import modules

    specs = modules.job_specs(manifests)
    with SessionLocal() as db:
        scheduled = schedule.tick(db, specs)
        stale = queue.requeue_stale(db)
    report = runner.run_pending(SessionLocal, modules.job_handlers(manifests), limit=limit,
                                lease_seconds=settings.jobs_lease_seconds)
    return {"scheduled": scheduled, "requeued": stale, "done": report.done, "retried": report.retried,
            "failed": report.failed}


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    from app.core.config import settings
    from app.core.db import SessionLocal
    from app.modules.jobs.application import schedule

    from . import modules, registry, schema_version

    registry.wire()
    schema_version.ensure_current()
    manifests = modules.discover()
    with SessionLocal() as db:
        schedule.sync(db, modules.job_specs(manifests))
    stop = threading.Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: stop.set())
    log.info("jobs: воркер очереди запущен, опрос каждые %d с", settings.jobs_poll_seconds)
    while not stop.is_set():
        try:
            counts = run_once(manifests)
        except Exception:                                # оборот не должен ронять воркер
            log.exception("jobs: оборот цикла завершился ошибкой")
            counts = {}
        busy = any(counts.get(k) for k in ("done", "retried", "failed"))
        if not busy:
            stop.wait(max(1, settings.jobs_poll_seconds))
    log.info("jobs: воркер остановлен")


if __name__ == "__main__":
    main()
