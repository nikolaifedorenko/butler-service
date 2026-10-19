"""Загруженные медиа (фото обходов/нарушений)."""
from __future__ import annotations

import datetime as dt
from typing import Optional

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base
from ..deps import now_local


class Photo(Base):
    """Фото и видео (комментарии к «Не ОК», замечания по возврату кара).

    Храним оригиналы на диске в data/uploads/YYYY/MM/, путь относительно BASE_DIR.
    media_type — "photo" (по умолчанию) или "video": у видео свой лимит размера
    (video_max_mb; 50 МБ — предел загрузки в Telegram Bot API) и свой срок хранения
    (video_retention_days). Колонка добавлена позже фото, поэтому у старых записей
    она пустая и трактуется как "photo".

    Срок хранения настраивается: старые файлы удаляет cleanup_photos() при старте
    сервера; запись остаётся (url пустой, missing=True) — комментарии не теряются.
    """

    __tablename__ = "photos"

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(32), index=True)   # night_item | car_return | car_check
    ref_id: Mapped[int] = mapped_column(Integer, index=True)    # id связанной записи
    filename: Mapped[str] = mapped_column(String(255), default="")
    path: Mapped[str] = mapped_column(String(400), default="")  # относительный путь от корня проекта
    size: Mapped[int] = mapped_column(Integer, default=0)
    media_type: Mapped[str] = mapped_column(String(8), default="photo")   # photo | video
    uploaded_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    uploaded_by_name: Mapped[str] = mapped_column(String(120), default="")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=now_local)


