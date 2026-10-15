"""Поддомен «Ночной отчёт»: области, чек-листы, отчёты, секции, пункты, перехваты."""
from __future__ import annotations

import datetime as dt
from typing import Optional

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db import Base
from ..deps import now_local

# ═══════════════════════ НОЧНОЙ ОТЧЁТ + ЭЛЕКТРОКАРЫ ═══════════════════════
# Времена событий (created_at/taken_at/…) хранятся в ЛОКАЛЬНОМ времени объекта
# (Europe/Moscow, naive) — как Punch.ts. Для этого нужен now_local(), а не utcnow().


class NightArea(Base):
    """Справочник областей ночной проверки (виллы, спа, бассейн, ресепшн…).

    name       — отображаемое название («Вилла VEG 4001», «Спа»);
    category   — категория области («VEG», «VPS», «Офис»): пункты чек-листа
                 привязаны к категории, поэтому у всех вилл одной категории
                 список пунктов одинаковый;
    active     — выключенные области не попадают в новые ночные отчёты
                 (созданные ранее отчёты не меняются: там лежит снимок).
    """

    __tablename__ = "night_areas"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160), unique=True)
    category: Mapped[str] = mapped_column(String(80), default="")
    sort_order: Mapped[int] = mapped_column(Integer, default=100)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=now_local)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime, default=now_local, onupdate=now_local)


class ChecklistItem(Base):
    """Пункт чек-листа области (ведётся админом/менеджером). Привязан к категории."""

    __tablename__ = "checklist_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    area_id: Mapped[int] = mapped_column(ForeignKey("night_areas.id"), index=True)
    text: Mapped[str] = mapped_column(String(300))
    sort_order: Mapped[int] = mapped_column(Integer, default=100)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=now_local)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime, default=now_local, onupdate=now_local)

    area: Mapped[NightArea] = relationship()


class NightReport(Base):
    """Ночной отчёт за смену 20:00–08:00. Создаётся автоматически на каждую ночь
    (или задним числом при старте сервера), автозакрывается в 08:00.

    date — дата НАЧАЛА смены (вечер); shift_label — человекочитаемая подпись смены.
    """

    __tablename__ = "night_reports"

    id: Mapped[int] = mapped_column(primary_key=True)
    date: Mapped[dt.date] = mapped_column(Date, unique=True, index=True)
    shift_label: Mapped[str] = mapped_column(String(80), default="Ночная смена 20:00–08:00")
    status: Mapped[str] = mapped_column(String(16), default="open")   # open | closed
    closed_at: Mapped[Optional[dt.datetime]] = mapped_column(DateTime, nullable=True)
    close_reason: Mapped[str] = mapped_column(String(16), default="")  # auto | manual
    result: Mapped[str] = mapped_column(String(16), default="")        # full | partial ('' пока открыт)
    cars_step_done: Mapped[bool] = mapped_column(Boolean, default=False)  # шаг «Проверка электрокаров» завершён
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=now_local)

    areas: Mapped[list[NightAreaSection]] = relationship(
        back_populates="report", cascade="all, delete-orphan", order_by="NightAreaSection.sort_order")


class NightAreaSection(Base):
    """Область внутри ночного отчёта — снимок справочника на момент создания отчёта.

    snapshot_json — [{"id": <item_id>, "text": "..."}]: правки справочников после
    создания отчёта его не ломают.
    """

    __tablename__ = "night_area_sections"
    __table_args__ = (UniqueConstraint("report_id", "area_id", name="uq_night_section_area"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    report_id: Mapped[int] = mapped_column(ForeignKey("night_reports.id"), index=True)
    area_id: Mapped[Optional[int]] = mapped_column(ForeignKey("night_areas.id"), nullable=True)
    name: Mapped[str] = mapped_column(String(160))
    category: Mapped[str] = mapped_column(String(80), default="")
    snapshot_json: Mapped[str] = mapped_column(Text, default="[]")
    sort_order: Mapped[int] = mapped_column(Integer, default=100)
    # кто ведёт проверку области сейчас
    taken_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    taken_by_name: Mapped[str] = mapped_column(String(120), default="")
    taken_at: Mapped[Optional[dt.datetime]] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="free")   # free | taken | done
    closed_at: Mapped[Optional[dt.datetime]] = mapped_column(DateTime, nullable=True)
    closed_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)

    report: Mapped[NightReport] = relationship(back_populates="areas")
    items: Mapped[list[NightCheckItem]] = relationship(
        back_populates="section", cascade="all, delete-orphan", order_by="NightCheckItem.sort_order")


class NightCheckItem(Base):
    """Пункт чек-листа области в конкретном отчёте (снимок + ответ батлера)."""

    __tablename__ = "night_check_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    section_id: Mapped[int] = mapped_column(ForeignKey("night_area_sections.id"), index=True)
    item_id: Mapped[Optional[int]] = mapped_column(ForeignKey("checklist_items.id"), nullable=True)
    text: Mapped[str] = mapped_column(String(300))
    sort_order: Mapped[int] = mapped_column(Integer, default=100)
    answer: Mapped[str] = mapped_column(String(8), default="")   # '' (не отмечено) | ok | bad
    comment: Mapped[str] = mapped_column(Text, default="")
    answered_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    answered_by_name: Mapped[str] = mapped_column(String(120), default="")
    answered_at: Mapped[Optional[dt.datetime]] = mapped_column(DateTime, nullable=True)

    section: Mapped[NightAreaSection] = relationship(back_populates="items")


class NightInterception(Base):
    """История перехватов областей: второй батлер забрал область, которая была в работе."""

    __tablename__ = "night_interceptions"

    id: Mapped[int] = mapped_column(primary_key=True)
    report_id: Mapped[int] = mapped_column(ForeignKey("night_reports.id"), index=True)
    section_id: Mapped[int] = mapped_column(ForeignKey("night_area_sections.id"), index=True)
    from_user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    from_user_name: Mapped[str] = mapped_column(String(120), default="")
    to_user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    to_user_name: Mapped[str] = mapped_column(String(120), default="")
    ts: Mapped[dt.datetime] = mapped_column(DateTime, default=now_local)


