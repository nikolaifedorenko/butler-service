"""Модели модуля «Шахматка» (спецификация §3). Кросс-модульных relationship нет (R6): связь
с сотрудниками — строковым FK на employees.id. Предупреждения не хранятся (§4.4), объект
строки покрытия — тоже (§3.4): оба вычисляются при чтении."""
from __future__ import annotations

import datetime as dt
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy import false as sa_false
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, Json
from app.core.external import ExternalRefColumns
from app.core.time import Moment, now

# ── 3.1 Фонд ───────────────────────────────────────────────────────────────


class Ooo(Base):
    """OOO — объект не в продаже: интервал по половинам суток [start/start_half, end/end_half]
    (спецификация OOO и блоков §3). Позиция половины — pos(день, AM|PM)."""

    __tablename__ = "stays_ooo"
    __table_args__ = (
        CheckConstraint("start_half IN ('AM', 'PM')", name="ck_stays_ooo_start_half"),
        CheckConstraint("end_half IN ('AM', 'PM')", name="ck_stays_ooo_end_half"),
        Index("ix_stays_ooo_unit_start", "unit_id", "start"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    unit_id: Mapped[int] = mapped_column(ForeignKey("fund_units.id"))
    start: Mapped[dt.date] = mapped_column(Date)
    end: Mapped[dt.date] = mapped_column(Date)
    start_half: Mapped[str] = mapped_column(String(2), default="AM")
    end_half: Mapped[str] = mapped_column(String(2), default="PM")
    reason: Mapped[str] = mapped_column(String(120), default="")
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[dt.datetime] = mapped_column(Moment, default=now)
    author_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)


class Block(Base):
    """Блок — резерв на категорию без привязки к объекту: количество по ночам и категориям
    лежит в BlockNight (спецификация OOO и блоков §3)."""

    __tablename__ = "stays_blocks"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(120), default="")
    start: Mapped[dt.date] = mapped_column(Date)
    end: Mapped[dt.date] = mapped_column(Date)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[dt.datetime] = mapped_column(Moment, default=now)
    author_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)


class BlockNight(Base):
    """Сколько объектов категории блок держит в ночь night (ночь D — от PM дня D до AM дня D+1)."""

    __tablename__ = "stays_block_nights"
    __table_args__ = (CheckConstraint("quantity >= 1", name="ck_stays_block_nights_quantity"),)

    block_id: Mapped[int] = mapped_column(ForeignKey("stays_blocks.id", ondelete="CASCADE"), primary_key=True)
    category_id: Mapped[int] = mapped_column(ForeignKey("fund_categories.id"), primary_key=True)
    night: Mapped[dt.date] = mapped_column(Date, primary_key=True)
    quantity: Mapped[int] = mapped_column(Integer)


class Label(Base):
    """Метка брони — цвет полосы на шахматке."""

    __tablename__ = "stays_labels"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(80), unique=True)
    color: Mapped[str] = mapped_column(String(9), default="#3b6fd8")


# ── 3.2 Гости ──────────────────────────────────────────────────────────────


# ── 3.3 Брони ──────────────────────────────────────────────────────────────


class StayGroup(Base):
    """Группа совместного проживания: брони в одном объекте, каждая на своего гостя."""

    __tablename__ = "stays_groups"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(120), default="")


class Reservation(ExternalRefColumns, Base):
    """Бронь. number (Fidelio) не уникален: совместные брони. version — защита от
    одновременной правки (§9: второе сохранение получает 409)."""

    __tablename__ = "stays_reservations"
    __table_args__ = (Index("ix_stays_res_dates", "check_in", "check_out"),
                      UniqueConstraint("ext_system", "ext_instance", "ext_id", name="uq_stays_res_external"))

    id: Mapped[int] = mapped_column(primary_key=True)
    number: Mapped[str] = mapped_column(String(40), default="", index=True)
    status: Mapped[str] = mapped_column(String(12), default="confirmed")
    check_in: Mapped[dt.date] = mapped_column(Date)
    check_out: Mapped[dt.date] = mapped_column(Date)
    early: Mapped[bool] = mapped_column(Boolean, default=False)
    late: Mapped[bool] = mapped_column(Boolean, default=False)
    category_id: Mapped[int] = mapped_column(ForeignKey("fund_categories.id"))
    paid_category_id: Mapped[Optional[int]] = mapped_column(ForeignKey("fund_categories.id"), nullable=True)
    label_id: Mapped[Optional[int]] = mapped_column(ForeignKey("stays_labels.id"), nullable=True)
    customer: Mapped[str] = mapped_column(String(160), default="")
    note: Mapped[str] = mapped_column(Text, default="")
    vip_code_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("guests_vip_codes.id", name="fk_stays_reservations_vip_code"), nullable=True)
    escort_mode: Mapped[str] = mapped_column(String(8), default="rules")   # rules | required | declined
    fields: Mapped[dict] = mapped_column(Json, default=dict)
    group_id: Mapped[Optional[int]] = mapped_column(ForeignKey("stays_groups.id"), nullable=True,
                                                    index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    search_text: Mapped[str] = mapped_column(String(1000), default="")
    created_at: Mapped[dt.datetime] = mapped_column(Moment, default=now)
    updated_at: Mapped[dt.datetime] = mapped_column(Moment, default=now, onupdate=now)


class Move(Base):
    """Переезд: с этой даты бронь живёт в другой категории (PoC §4.6)."""

    __tablename__ = "stays_moves"
    __table_args__ = (UniqueConstraint("reservation_id", "move_date", name="uq_stays_move"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    reservation_id: Mapped[int] = mapped_column(ForeignKey("stays_reservations.id"))
    move_date: Mapped[dt.date] = mapped_column(Date)
    category_id: Mapped[int] = mapped_column(ForeignKey("fund_categories.id"))


class Assignment(Base):
    """Часть сегмента брони → объект; pinned — закреплён вручную (PoC §4.8).

    seg_index — индекс части: сегмент * PIECE_BASE + номер части между границами версий фонда
    (ревизия 0011; спецификация версий §5). start_pos — начало части (позиция половинки, пишется
    у каждой строки): часть режется ещё и там, где заселённый гость переехал из-за OOO (ревизия
    0016), — читатели режут сегменты по границам версий и по start_pos строк брони.
    pin_unit_id — объект закрепления у закреплённой части без объекта (овербукинг под OOO, §4.4)."""

    __tablename__ = "stays_assignments"
    __table_args__ = (UniqueConstraint("reservation_id", "seg_index", name="uq_stays_assignment"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    reservation_id: Mapped[int] = mapped_column(ForeignKey("stays_reservations.id"))
    seg_index: Mapped[int] = mapped_column(Integer)
    unit_id: Mapped[Optional[int]] = mapped_column(ForeignKey("fund_units.id"), nullable=True,
                                                   index=True)
    pinned: Mapped[bool] = mapped_column(Boolean, default=False)
    start_pos: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    pin_unit_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("fund_units.id", name="fk_stays_assignments_pin_unit"), nullable=True)


class Occupant(Base):
    """Проживающий: гость брони со своими датами; main — главный на эти даты."""

    __tablename__ = "stays_occupants"

    id: Mapped[int] = mapped_column(primary_key=True)
    reservation_id: Mapped[int] = mapped_column(ForeignKey("stays_reservations.id"), index=True)
    guest_id: Mapped[int] = mapped_column(ForeignKey("guests.id"), index=True)
    date_from: Mapped[dt.date] = mapped_column(Date)
    date_to: Mapped[dt.date] = mapped_column(Date)
    role: Mapped[str] = mapped_column(String(8), default="guest")   # main | guest


class Companion(Base):
    """Разовый сопровождающий брони без профиля: охрана, водитель, няня, животное."""

    __tablename__ = "stays_companions"

    id: Mapped[int] = mapped_column(primary_key=True)
    reservation_id: Mapped[int] = mapped_column(ForeignKey("stays_reservations.id"), index=True)
    kind: Mapped[str] = mapped_column(String(16), default="other")
    description: Mapped[str] = mapped_column(String(255), default="")


class Logistics(Base):
    """Рейс, трансфер или автомобиль брони."""

    __tablename__ = "stays_logistics"

    id: Mapped[int] = mapped_column(primary_key=True)
    reservation_id: Mapped[int] = mapped_column(ForeignKey("stays_reservations.id"), index=True)
    kind: Mapped[str] = mapped_column(String(12), default="transfer")   # flight | transfer | car
    date: Mapped[Optional[dt.date]] = mapped_column(Date, nullable=True)
    time: Mapped[str] = mapped_column(String(5), default="")
    description: Mapped[str] = mapped_column(String(255), default="")


# ── 3.4 Покрытие батлерами ─────────────────────────────────────────────────


class Escort(Base):
    """Список «Сопровождают гостей»: кто из сотрудников может вести гостей."""

    __tablename__ = "stays_escorts"

    id: Mapped[int] = mapped_column(primary_key=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), unique=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class CoverageLine(Base):
    """Строка покрытия: на дату батлер ведёт всю бронь, всю группу или выбранных
    гостей (stays_coverage_guests). Объект не хранится — он вычисляется."""

    __tablename__ = "stays_coverage"
    __table_args__ = (
        CheckConstraint("(reservation_id IS NULL) <> (group_id IS NULL)",
                        name="ck_stays_coverage_target"),
        Index("ix_stays_coverage_emp_day", "employee_id", "day"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    day: Mapped[dt.date] = mapped_column(Date, index=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"))
    reservation_id: Mapped[Optional[int]] = mapped_column(ForeignKey("stays_reservations.id"),
                                                          nullable=True, index=True)
    group_id: Mapped[Optional[int]] = mapped_column(ForeignKey("stays_groups.id"), nullable=True)
    source: Mapped[str] = mapped_column(String(8), default="manual")    # template | manual
    overnight: Mapped[bool] = mapped_column(Boolean, default=False)
    comment: Mapped[str] = mapped_column(String(255), default="")


class CoverageGuest(Base):
    """Выбранные гости строки покрытия; пусто — вся бронь или группа. Ссылка на гостя, а не
    на запись проживающего: при смене главного запись меняется, а батлер ведёт человека.
    Удаляется кодом вместе со строкой (на SQLite внешние ключи не проверяются)."""

    __tablename__ = "stays_coverage_guests"

    coverage_id: Mapped[int] = mapped_column(ForeignKey("stays_coverage.id"), primary_key=True)
    guest_id: Mapped[int] = mapped_column(ForeignKey("guests.id"), primary_key=True)


# ── 3.5 Настройки и настраиваемые поля ─────────────────────────────────────


class StaysSettings(Base):
    """Настройки модуля, одна строка id=1 (её заводит ревизия 0008)."""

    __tablename__ = "stays_settings"

    id: Mapped[int] = mapped_column(primary_key=True)
    special_factor: Mapped[Decimal] = mapped_column(Numeric(4, 2), default=Decimal("2"))
    daily_limit: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("8"))
    # коды дня Табеля, при которых назначенному батлеру нужна подмена (отпуск, больничный…)
    replacement_codes: Mapped[str] = mapped_column(String(120), default="ОТ,ДО,Б,ОВ,К")
    # «Шахматка в эксплуатации» (§9.3): true — начальная загрузка («заменить всё») недоступна
    in_production: Mapped[bool] = mapped_column(Boolean, default=False, server_default=sa_false())
