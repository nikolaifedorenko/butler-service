"""Сверки ответственных служб для экрана «Настройки → Обзор»."""
from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..adapters.orm import ResponsibilityService


def overview_checks(db: Session) -> list[dict]:
    """Активные службы без настроенного канала доставки."""
    out: list[dict] = []
    for s in db.scalars(select(ResponsibilityService)
                        .where(ResponsibilityService.active.is_(True))
                        .order_by(ResponsibilityService.sort_order, ResponsibilityService.id)):
        chats = json.loads(s.chat_ids or "[]")
        tg_ready = bool(s.use_telegram and chats)
        mail_ready = bool(s.use_email and "@" in (s.email_to or ""))
        if not (tg_ready or mail_ready):
            out.append({"code": "APP-SVC-NO-CHANNEL", "level": "warn", "screen": "night",
                        "text": (f"Ответственная служба «{s.name}»: канал доставки не настроен — "
                                 f"недостатки по её пунктам никуда не отправляются "
                                 f"(«Настройки → Ночной обход → Службы»)")})
    return out
