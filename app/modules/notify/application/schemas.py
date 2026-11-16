"""Модели данных доставки, которые отдаёт прикладной слой — в том числе разделам-отправителям."""
from __future__ import annotations

from typing import Any, Optional

from app.core.schemas import ApiModel


class DispatchOut(ApiModel):
    """Строка журнала отправок: одно сообщение одному получателю по одному каналу."""

    id: int
    domain: str
    ref_id: Optional[int]
    ts: Optional[str]
    actor_name: str
    recipient_id: Optional[int]
    recipient_name: str
    channel: str
    channel_title: str
    target: str
    subject: str
    message: str
    items: list[dict[str, Any]]     # состав отправки, как он был на момент отправки
    items_count: int
    media_count: int
    status: str
    status_title: str
    error: str
    external_id: str
    attempts: int
    can_retry: bool
