"""Журнал аудита: модель AuditLog и функция audit() (ядро, R5).

Перенесено в core в фазе C1 (20.10.2026): AuditLog был в app/models/audit.py,
audit() — в app/auth.py. Запись журнала — сквозная инфраструктура: её вызывают
и api-роутеры, и сервисы, и (позже) интерфейсы модулей.
"""
from __future__ import annotations

import datetime as dt
import json
from typing import TYPE_CHECKING, Optional

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, Session, mapped_column, relationship

from .db import Base
from .time import utcnow

if TYPE_CHECKING:
    from .auth import Principal
    from .identity import User


class AuditLog(Base):
    """Кто и что менял (график, ручные отметки, настройки)."""

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    ts: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow, index=True)
    actor_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    actor_name: Mapped[str] = mapped_column(String(120), default="")
    action: Mapped[str] = mapped_column(String(64))
    target: Mapped[str] = mapped_column(String(200), default="")
    payload_json: Mapped[str] = mapped_column(Text, default="{}")

    actor: Mapped[Optional[User]] = relationship()  # noqa: F821 — разрешается реестром (User в core.identity)


def audit(db: Session, principal: Optional[Principal], action: str, target: str = "",
          payload: Optional[dict] = None) -> None:
    """Запись в журнал аудита (без commit — вызывающий код сам коммитит)."""
    db.add(AuditLog(
        actor_id=principal.user.id if principal else None,
        actor_name=(principal.name + (" (как сотрудник)" if principal.impersonated else "")) if principal else "system",
        action=action, target=target, payload_json=json.dumps(payload or {}, ensure_ascii=False, default=str),
        ts=utcnow(),
    ))
