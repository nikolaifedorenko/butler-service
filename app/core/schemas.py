"""Модели ответов API (ADR-0013, раздел 4)."""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class ApiModel(BaseModel):
    """Основа модели ответа: поле, которого нет в модели, — ошибка, а не молча отброшенные данные."""

    model_config = ConfigDict(extra="forbid")


class Ok(ApiModel):
    """Ответ операции, у которой нет данных для интерфейса."""

    ok: bool = True
