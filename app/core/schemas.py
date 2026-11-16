"""Модели ответов API (ADR-0013, раздел 4)."""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict


class ApiModel(BaseModel):
    """Основа модели ответа: поле, которого нет в модели, — ошибка, а не молча отброшенные данные."""

    model_config = ConfigDict(extra="forbid")


class PhotoOut(ApiModel):
    """Фото или видео, приложенное к записи (``core.media.photos_of``)."""

    id: int
    filename: str
    size: int
    media_type: str
    url: str                    # пусто, если файла уже нет
    missing: bool
    uploaded_by_name: str
    created_at: Optional[str]   # местное время объекта


class Ok(ApiModel):
    """Ответ операции, у которой нет данных для интерфейса."""

    ok: bool = True
