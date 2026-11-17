"""Фоновая задача ночного отчёта: досоздать наступившие смены и автозакрыть прошедшие дедлайн 08:00.

GET-запросы раздела читают базу без записей; это обслуживание делает воркер очереди (модуль jobs)
по расписанию из манифеста. Ручное переоткрытие отчёта задача не закрывает (``reopened_at``).
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from .night import sync_reports


def sync_reports_job(db: Session, payload: dict) -> dict:
    """Один раунд обслуживания; возвращает результат ``sync_reports``."""
    return sync_reports(db, force=True)
