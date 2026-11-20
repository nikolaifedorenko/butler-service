"""Метрики состояния для Prometheus: очередь задач и сервис PDF (дополнение к метрикам запросов из
core/observability.py). Считаются при каждом чтении /metrics; сбой источника не роняет остальное."""
from __future__ import annotations

import logging

log = logging.getLogger("uvicorn.error")


class StateCollector:
    """Подключается к реестру prometheus_client: collect() вызывается при каждом скрейпе."""

    def collect(self):
        from prometheus_client.core import GaugeMetricFamily

        from app.core.db import SessionLocal
        from app.modules.exchange.application import documents
        from app.modules.jobs.application import stats

        lag = GaugeMetricFamily("tt_jobs_schedule_lag_seconds",
                                "На сколько секунд просрочено расписание задачи (0 — в срок)", labels=["job"])
        depth = GaugeMetricFamily("tt_jobs_queue", "Задач в очереди по статусам", labels=["status"])
        failed = GaugeMetricFamily("tt_jobs_failed_24h", "Задач, окончательно проваленных за сутки")
        overdue = GaugeMetricFamily("tt_jobs_overdue", "Расписаний, просроченных настолько, что воркер, вероятно, стоит")
        try:
            with SessionLocal() as db:
                for name, seconds in stats.schedule_lags(db).items():
                    lag.add_metric([name], seconds)
                for status, count in stats.queue_counts(db).items():
                    depth.add_metric([status], count)
                failed.add_metric([], stats.failed_since(db))
                overdue.add_metric([], len(stats.overdue(db)))
        except Exception:                                # метрики не должны ронять скрейп
            log.exception("metrics: не удалось прочитать состояние очереди")
        yield from (lag, depth, failed, overdue)

        pdf = GaugeMetricFamily("tt_pdf_available", "Сервис PDF (Gotenberg) отвечает: 1 — да, 0 — нет")
        try:
            pdf.add_metric([], 0 if documents.pdf_error() else 1)
        except Exception:
            pdf.add_metric([], 0)
        yield pdf


def register() -> None:
    from app.core import observability

    observability.register_collector(StateCollector())
