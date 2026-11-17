"""Фоновая задача уведомлений: доотправка очереди (outbox).

Строки, которые запрос не успел отправить (процесс упал), и пометка застрявших в ``sending``
выполняются воркером очереди по расписанию из манифеста — страховка к отправке сразу после запроса.
"""
from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from .dispatch import fail_stale_sending, run_outbox

log = logging.getLogger("uvicorn.error")


def outbox_job(db: Session, payload: dict) -> dict:
    """Пометить прерванные отправки и доотправить очередь; возвращает счётчики."""
    stale = fail_stale_sending(db)
    sent = run_outbox(db)
    if stale:
        log.warning("notify_outbox: доставок со статусом «неизвестно» (прерваны перезапуском): %d", stale)
    if sent:
        log.info("notify_outbox: доотправлено из очереди: %d", len(sent))
    return {"stale": stale, "sent": len(sent)}
