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
    """Фотографии (комментарии к «Не ОК», замечания по возврату кара).

    Храним оригиналы на диске в data/uploads/YYYY/MM/, путь относительно BASE_DIR.
    Срок хранения настраивается (photo_retention_days): старые файлы удаляет
    cleanup_photos() при старте сервера; запись остаётся (url пустой, missing=True).
    """

    __tablename__ = "photos"

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(32), index=True)   # night_item | car_return | car_check
    ref_id: Mapped[int] = mapped_column(Integer, index=True)    # id связанной записи
    filename: Mapped[str] = mapped_column(String(255), default="")
    path: Mapped[str] = mapped_column(String(400), default="")  # относительный путь от корня проекта
    size: Mapped[int] = mapped_column(Integer, default=0)
    uploaded_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    uploaded_by_name: Mapped[str] = mapped_column(String(120), default="")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=now_local)


