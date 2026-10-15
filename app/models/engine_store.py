"""Хранилище расчётного движка: Табель, модификаторы дней, версии настроек,
закрытия периодов, отложенные переносы, ключ-значение Setting."""
from __future__ import annotations

import datetime as dt
from typing import Optional

from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base
from .common import utcnow


class Setting(Base):
    """Ключ/значение — правила расчёта, редактируются в веб-интерфейсе."""

    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(String(255), default="")
    description: Mapped[str] = mapped_column(String(255), default="")


# ═══════════════════════ НОЧНОЙ ОТЧЁТ + ЭЛЕКТРОКАРЫ ═══════════════════════
# Времена событий (created_at/taken_at/…) хранятся в ЛОКАЛЬНОМ времени объекта
# (Europe/Moscow, naive) — как Punch.ts. Для этого нужен now_local(), а не utcnow().




# ═══════════════════════ ДВИЖОК v4: Табель, настройки, закрытия, права ═══════════════════════


class TabelDay(Base):
    """Табель (первичный документ): код дня + плановые часы. Независим от Графика (спец. 4.8)."""

    __tablename__ = "tabel_days"
    __table_args__ = (UniqueConstraint("employee_id", "date", name="uq_tabel_emp_date"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), index=True)
    date: Mapped[dt.date] = mapped_column(Date, index=True)
    code: Mapped[str] = mapped_column(String(12))                 # Я / Н / К / В / ОТ / ДО / Б …
    plan_minutes: Mapped[int] = mapped_column(Integer, default=0)
    note: Mapped[str] = mapped_column(String(255), default="")
    source: Mapped[str] = mapped_column(String(16), default="manual")   # manual | schedule
    updated_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class EngineSettingsVersion(Base):
    """Версия справочников Т1–Т7, Т9, Т-Группы. Действует с valid_from; ретро-исправление —
    новая версия с тем же valid_from (берётся последняя по id)."""

    __tablename__ = "engine_settings_versions"

    id: Mapped[int] = mapped_column(primary_key=True)
    valid_from: Mapped[dt.date] = mapped_column(Date, index=True)
    payload_json: Mapped[str] = mapped_column(Text)
    note: Mapped[str] = mapped_column(String(255), default="")
    created_by_name: Mapped[str] = mapped_column(String(120), default="")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)


class DayModifier(Base):
    """Модификатор календарного дня Т4: имя, значение и область (сотрудник / группа / все;
    конкретный день или весь период-месяц)."""

    __tablename__ = "day_modifiers"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(32))                  # double_overtime | pays_overtime | …
    value: Mapped[str] = mapped_column(String(8))                  # "1" | "0" | "auto"
    employee_id: Mapped[Optional[int]] = mapped_column(ForeignKey("employees.id"), nullable=True)
    group: Mapped[str] = mapped_column(String(80), default="")
    date: Mapped[Optional[dt.date]] = mapped_column(Date, nullable=True, index=True)
    period_start: Mapped[Optional[dt.date]] = mapped_column(Date, nullable=True, index=True)
    note: Mapped[str] = mapped_column(String(255), default="")
    created_by_name: Mapped[str] = mapped_column(String(120), default="")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)


class PeriodClosing(Base):
    """Закрытие периода сотрудника: результат, закрывающий банк, входной снимок, версии настроек."""

    __tablename__ = "period_closings"
    __table_args__ = (UniqueConstraint("employee_id", "period_start", name="uq_closing_emp_period"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), index=True)
    period_start: Mapped[dt.date] = mapped_column(Date)
    period_end: Mapped[dt.date] = mapped_column(Date)
    step_minutes: Mapped[int] = mapped_column(Integer, default=60)
    previous_step_minutes: Mapped[int] = mapped_column(Integer, default=60)
    bank_open_minutes: Mapped[int] = mapped_column(Integer, default=0)
    deferred_in_json: Mapped[str] = mapped_column(Text, default="[]")
    closing_bank_minutes: Mapped[int] = mapped_column(Integer, default=0)
    settings_versions: Mapped[str] = mapped_column(String(255), default="")
    result_json: Mapped[str] = mapped_column(Text, default="{}")
    flags_json: Mapped[str] = mapped_column(Text, default="{}")   # снимок FlagsResult (7.2)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    closed_by_name: Mapped[str] = mapped_column(String(120), default="")
    closed_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)


class DeferredCarry(Base):
    """Отложенные блоки кодов УТ, переданные во вход следующего периода (CarryOverPort)."""

    __tablename__ = "deferred_carry"

    id: Mapped[int] = mapped_column(primary_key=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), index=True)
    period_start: Mapped[dt.date] = mapped_column(Date, index=True)   # период-получатель
    source_day: Mapped[dt.date] = mapped_column(Date)
    tariff: Mapped[str] = mapped_column(String(12))
    minutes: Mapped[int] = mapped_column(Integer)
    # v7/R1: у DeferredBlock нет reason_code — причина неразмещения запись NO_RECEIVER;
    # колонка reason_code старой схемы не мапится (base 15 «Миграция прототипа»)


