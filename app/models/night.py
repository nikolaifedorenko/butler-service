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

from ..core.db import Base
from ..core.time import now_local

# ═══════════════════════ НОЧНОЙ ОТЧЁТ + ЭЛЕКТРОКАРЫ ═══════════════════════
# Времена событий (created_at/taken_at/…) хранятся в ЛОКАЛЬНОМ времени объекта
# (Europe/Moscow, naive) — как Punch.ts. Для этого нужен now_local(), а не utcnow().


class NightZone(Base):
    """Зона обхода — ПЕРВЫЙ уровень навигации ночного отчёта (v2, 19.10.2026).

    Зоны выросли из текстовых «категорий» областей: «Семейные виллы»,
    «Президентские винные виллы», «Офисы». Внутри зоны — объекты (NightArea):
    «Вилла 4001»…«Вилла 4012»; чек-лист задаётся НА ЗОНУ (ChecklistItem.zone_id),
    поэтому у всех однотипных объектов он одинаковый, а индивидуальные особенности
    объекта правятся точечно (ChecklistOverride).

    sort_order — порядок зон в обходе; active=False — зона не предлагается новым
    объектам и не попадает в новые отчёты (созданные ранее не меняются: там снимок).
    """

    __tablename__ = "night_zones"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160), unique=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=100)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=now_local)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime, default=now_local, onupdate=now_local)

    areas: Mapped[list[NightArea]] = relationship(back_populates="zone")


class NightArea(Base):
    """Объект ночной проверки — ВТОРОЙ уровень навигации (вилла, спа, офис…).

    name       — отображаемое название («Вилла 4001», «Зона SPA»);
    zone_id    — зона обхода (NightZone): чек-лист зоны действует для всех её объектов;
    category   — ИСТОРИЧЕСКАЯ текстовая группа («общие зоны», «служебные»). Зоны v2
                 созданы из этих категорий миграцией migrate_night_zones(); поле
                 сохранено, чтобы закрытые отчёты и выгрузки не потеряли группировку;
    active     — выключенные объекты не попадают в новые ночные отчёты
                 (созданные ранее отчёты не меняются: там лежит снимок).
    """

    __tablename__ = "night_areas"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160), unique=True)
    zone_id: Mapped[Optional[int]] = mapped_column(ForeignKey("night_zones.id"), nullable=True, index=True)
    category: Mapped[str] = mapped_column(String(80), default="")
    sort_order: Mapped[int] = mapped_column(Integer, default=100)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=now_local)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime, default=now_local, onupdate=now_local)

    zone: Mapped[Optional[NightZone]] = relationship(back_populates="areas")


class ZoneChecklistItem(Base):
    """Пункт ШАБЛОНА ЗОНЫ (v2, 19.10.2026): действует для всех объектов зоны.

    Основной режим чек-листа: «Витражи закрыты», «Свет выключен» задаются один раз
    на зону «Семейные виллы» и попадают в чек-лист всех 12 вилл. Индивидуальные
    особенности объекта (своя формулировка, отключение) — ChecklistOverride, а свой
    пункт только одного объекта — ChecklistItem(area_id=…).

    Отдельная таблица (а не zone_id в checklist_items) — сознательно: в существующих
    базах checklist_items.area_id NOT NULL, и ослабление потребовало бы пересоздания
    таблицы вместе с FK (на PostgreSQL — с каскадом). Проект держится «лёгких»
    миграций (ADD COLUMN / CREATE TABLE), поэтому шаблон зоны живёт своей таблицей.
    """

    __tablename__ = "zone_checklist_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    zone_id: Mapped[int] = mapped_column(ForeignKey("night_zones.id"), index=True)
    text: Mapped[str] = mapped_column(String(300))
    # ответственная служба (этап 3): кто получает недостаток по этому пункту
    service_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("responsibility_services.id"), nullable=True, index=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=100)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=now_local)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime, default=now_local, onupdate=now_local)

    zone: Mapped[NightZone] = relationship()


class ChecklistItem(Base):
    """Пункт чек-листа ОТДЕЛЬНОГО объекта (индивидуальный, не из шаблона зоны).

    Пример: «Детская кроватка установлена» только у «Виллы 4001». Общие для зоны
    пункты — ZoneChecklistItem; правка пункта шаблона у конкретного объекта —
    ChecklistOverride.
    """

    __tablename__ = "checklist_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    area_id: Mapped[int] = mapped_column(ForeignKey("night_areas.id"), index=True)
    text: Mapped[str] = mapped_column(String(300))
    service_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("responsibility_services.id"), nullable=True, index=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=100)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=now_local)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime, default=now_local, onupdate=now_local)

    area: Mapped[NightArea] = relationship()


class ChecklistOverride(Base):
    """Индивидуальные особенности объекта: шаблон зоны остаётся общим (v2).

    area_id + zone_item_id — у какого объекта правится какой пункт шаблона зоны;
    disabled=True — пункт у этого объекта не проверяется (не попадает в отчёт);
    text          — своя формулировка ('' = как в шаблоне зоны).

    Свои пункты объекта хранятся не здесь, а как ChecklistItem(area_id=…) —
    отдельная сущность для них не нужна.
    """

    __tablename__ = "checklist_overrides"
    __table_args__ = (UniqueConstraint("area_id", "zone_item_id", name="uq_checklist_override_area_item"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    area_id: Mapped[int] = mapped_column(ForeignKey("night_areas.id"), index=True)
    zone_item_id: Mapped[int] = mapped_column(ForeignKey("zone_checklist_items.id"), index=True)
    text: Mapped[str] = mapped_column(String(300), default="")
    disabled: Mapped[bool] = mapped_column(Boolean, default=False)
    # своя служба у этого объекта (None = как в шаблоне зоны)
    service_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("responsibility_services.id"), nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=now_local)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime, default=now_local, onupdate=now_local)

    area: Mapped[NightArea] = relationship()
    zone_item: Mapped[ZoneChecklistItem] = relationship()


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

    snapshot_json — [{"id": <item_id|zone_item_id>, "src": "zone"|"area", "text": "...",
    "overridden": bool}]: эффективный чек-лист объекта (шаблон зоны + свои пункты −
    отключённые у объекта, со своими формулировками) фиксируется при создании отчёта,
    поэтому правки справочников позже его не ломают.
    """

    __tablename__ = "night_area_sections"
    __table_args__ = (UniqueConstraint("report_id", "area_id", name="uq_night_section_area"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    report_id: Mapped[int] = mapped_column(ForeignKey("night_reports.id"), index=True)
    area_id: Mapped[Optional[int]] = mapped_column(ForeignKey("night_areas.id"), nullable=True)
    name: Mapped[str] = mapped_column(String(160))
    category: Mapped[str] = mapped_column(String(80), default="")
    # зона снимком (id + название): переименование/отключение зоны не меняет прошлые смены
    zone_id: Mapped[Optional[int]] = mapped_column(ForeignKey("night_zones.id"), nullable=True)
    zone_name: Mapped[str] = mapped_column(String(160), default="")
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
    # пункт из шаблона зоны (v2): item_id и zone_item_id — ровно один из двух
    zone_item_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("zone_checklist_items.id"), nullable=True)
    text: Mapped[str] = mapped_column(String(300))
    sort_order: Mapped[int] = mapped_column(Integer, default=100)
    # служба — снимком (id + название): переименование службы не меняет закрытые смены
    service_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("responsibility_services.id"), nullable=True, index=True)
    service_name: Mapped[str] = mapped_column(String(160), default="")
    answer: Mapped[str] = mapped_column(String(8), default="")   # '' (не отмечено) | ok | bad
    comment: Mapped[str] = mapped_column(Text, default="")
    answered_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    answered_by_name: Mapped[str] = mapped_column(String(120), default="")
    answered_at: Mapped[Optional[dt.datetime]] = mapped_column(DateTime, nullable=True)
    # отправка недостатка службе (этап 5): отправленное помечается и повторно не шлётся.
    # Если пункт исправили ПОСЛЕ отправки, ничего не отправляем и не отзываем —
    # в интерфейсе это видно как «исправлено после отправки».
    dispatch_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("notify_dispatches.id"), nullable=True)
    dispatched_at: Mapped[Optional[dt.datetime]] = mapped_column(DateTime, nullable=True)

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


