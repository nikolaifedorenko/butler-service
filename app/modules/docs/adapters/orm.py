"""ORM-модели модуля docs: виды заявлений."""
from __future__ import annotations

import datetime as dt

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.core.time import utcnow


class StatementKind(Base):
    """Вид заявления — расширяемый словарь (заменяет хардкод DOC_TYPES).

    code  — ключ привязки (ShiftType.doc_type) и имя файла фирменного бланка
            templates/<code>.docx;
    name  — человекочитаемое название для списков;
    text  — текст-заполнитель с плейсхолдерами {field}: используется,
            если фирменный бланк .docx не загружен;
    builtin — вид из комплекта системы (при первом запуске seeding-уется
            текстами из настроек/дефолтов)."""

    __tablename__ = "statement_kinds"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(40), unique=True)
    name: Mapped[str] = mapped_column(String(160))
    text: Mapped[str] = mapped_column(Text, default="")
    builtin: Mapped[bool] = mapped_column(Boolean, default=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True)   # показывать ли в списках выбора
    sort_order: Mapped[int] = mapped_column(Integer, default=100)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)
