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
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.core.time import now_local

# ── 3.1 Фонд ───────────────────────────────────────────────────────────────


class Category(Base):
    """Категория объекта: вид, сопровождение батлером, вес нагрузки."""

    __tablename__ = "stays_categories"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(16), unique=True)
    title: Mapped[str] = mapped_column(String(120))
    kind: Mapped[str] = mapped_column(String(16), default="room")    # villa | estate | apartment | room
    escorted: Mapped[bool] = mapped_column(Boolean, default=False)
    weight: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("1"))
    sort_order: Mapped[int] = mapped_column(Integer, default=100)


class Unit(Base):
    """Физический объект: номер, вилла, имение, апартаменты."""

    __tablename__ = "stays_units"

    id: Mapped[int] = mapped_column(primary_key=True)
    label: Mapped[str] = mapped_column(String(40), unique=True)
    category_id: Mapped[int] = mapped_column(ForeignKey("stays_categories.id"), index=True)
    building: Mapped[str] = mapped_column(String(40), default="")
    floor: Mapped[str] = mapped_column(String(8), default="")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=100)


class Hold(Base):
    """Блок или OOO: занимает объект целыми сутками с–по (PoC §5.2)."""

    __tablename__ = "stays_holds"
    __table_args__ = (Index("ix_stays_holds_unit_start", "unit_id", "start"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    unit_id: Mapped[int] = mapped_column(ForeignKey("stays_units.id"))
    start: Mapped[dt.date] = mapped_column(Date)
    end: Mapped[dt.date] = mapped_column(Date)
    kind: Mapped[str] = mapped_column(String(8), default="block")    # block | ooo
    title: Mapped[str] = mapped_column(String(120), default="")


class Label(Base):
    """Метка брони — цвет полосы на шахматке."""

    __tablename__ = "stays_labels"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(80), unique=True)
    color: Mapped[str] = mapped_column(String(9), default="#3b6fd8")


# ── 3.2 Гости ──────────────────────────────────────────────────────────────


class Guest(Base):
    """Профиль гостя. Уровень VIP/VVIP — свойство человека, переходит на все его брони."""

    __tablename__ = "stays_guests"

    id: Mapped[int] = mapped_column(primary_key=True)
    last_name: Mapped[str] = mapped_column(String(80))
    first_name: Mapped[str] = mapped_column(String(80), default="")
    middle_name: Mapped[str] = mapped_column(String(80), default="")
    phone: Mapped[str] = mapped_column(String(24), default="")      # нормализованный: +79161234567
    email: Mapped[str] = mapped_column(String(120), default="")
    birth_date: Mapped[Optional[dt.date]] = mapped_column(Date, nullable=True)
    level: Mapped[str] = mapped_column(String(8), default="regular")  # regular | vip | vvip
    preferences_json: Mapped[str] = mapped_column(Text, default="{}")
    special_dates_json: Mapped[str] = mapped_column(Text, default="[]")
    fields_json: Mapped[str] = mapped_column(Text, default="{}")
    note: Mapped[str] = mapped_column(Text, default="")
    external_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    source: Mapped[str] = mapped_column(String(16), default="")
    # нижний регистр Python: SQLite lower() кириллицу не понижает
    search_text: Mapped[str] = mapped_column(String(1000), default="")   # поиск подстрокой: индекс не помогает
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=now_local)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime, default=now_local, onupdate=now_local)


class GuestLink(Base):
    """Связь «кто кому»: одна строка, подпись для каждой стороны — LINK_KINDS."""

    __tablename__ = "stays_guest_links"
    __table_args__ = (UniqueConstraint("guest_a_id", "guest_b_id", "kind", name="uq_stays_guest_link"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    guest_a_id: Mapped[int] = mapped_column(ForeignKey("stays_guests.id"), index=True)
    guest_b_id: Mapped[int] = mapped_column(ForeignKey("stays_guests.id"), index=True)
    kind: Mapped[str] = mapped_column(String(16))


# ── 3.3 Брони ──────────────────────────────────────────────────────────────


class StayGroup(Base):
    """Группа совместного проживания: брони в одном объекте, каждая на своего гостя."""

    __tablename__ = "stays_groups"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(120), default="")


class Reservation(Base):
    """Бронь. number (Fidelio) не уникален: совместные брони. version — защита от
    одновременной правки (§9: второе сохранение получает 409)."""

    __tablename__ = "stays_reservations"
    __table_args__ = (Index("ix_stays_res_dates", "check_in", "check_out"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    number: Mapped[str] = mapped_column(String(40), default="", index=True)
    status: Mapped[str] = mapped_column(String(12), default="confirmed")
    check_in: Mapped[dt.date] = mapped_column(Date)
    check_out: Mapped[dt.date] = mapped_column(Date)
    early: Mapped[bool] = mapped_column(Boolean, default=False)
    late: Mapped[bool] = mapped_column(Boolean, default=False)
    category_id: Mapped[int] = mapped_column(ForeignKey("stays_categories.id"))
    paid_by: Mapped[str] = mapped_column(String(120), default="")
    label_id: Mapped[Optional[int]] = mapped_column(ForeignKey("stays_labels.id"), nullable=True)
    customer: Mapped[str] = mapped_column(String(160), default="")
    purpose: Mapped[str] = mapped_column(String(160), default="")
    note: Mapped[str] = mapped_column(Text, default="")
    declined_butler: Mapped[bool] = mapped_column(Boolean, default=False)
    fields_json: Mapped[str] = mapped_column(Text, default="{}")
    external_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    source: Mapped[str] = mapped_column(String(16), default="")
    group_id: Mapped[Optional[int]] = mapped_column(ForeignKey("stays_groups.id"), nullable=True,
                                                    index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    search_text: Mapped[str] = mapped_column(String(1000), default="")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=now_local)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime, default=now_local, onupdate=now_local)


class Move(Base):
    """Переезд: с этой даты бронь живёт в другой категории (PoC §4.6)."""

    __tablename__ = "stays_moves"
    __table_args__ = (UniqueConstraint("reservation_id", "move_date", name="uq_stays_move"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    reservation_id: Mapped[int] = mapped_column(ForeignKey("stays_reservations.id"))
    move_date: Mapped[dt.date] = mapped_column(Date)
    category_id: Mapped[int] = mapped_column(ForeignKey("stays_categories.id"))


class Assignment(Base):
    """Сегмент брони → объект; pinned — закреплён вручную (PoC §4.8)."""

    __tablename__ = "stays_assignments"
    __table_args__ = (UniqueConstraint("reservation_id", "seg_index", name="uq_stays_assignment"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    reservation_id: Mapped[int] = mapped_column(ForeignKey("stays_reservations.id"))
    seg_index: Mapped[int] = mapped_column(Integer)
    unit_id: Mapped[Optional[int]] = mapped_column(ForeignKey("stays_units.id"), nullable=True,
                                                   index=True)
    pinned: Mapped[bool] = mapped_column(Boolean, default=False)


class Occupant(Base):
    """Проживающий: гость брони со своими датами; main — главный на эти даты."""

    __tablename__ = "stays_occupants"

    id: Mapped[int] = mapped_column(primary_key=True)
    reservation_id: Mapped[int] = mapped_column(ForeignKey("stays_reservations.id"), index=True)
    guest_id: Mapped[int] = mapped_column(ForeignKey("stays_guests.id"), index=True)
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
    guest_id: Mapped[int] = mapped_column(ForeignKey("stays_guests.id"), primary_key=True)


# ── 3.5 Настройки и настраиваемые поля ─────────────────────────────────────


class CustomField(Base):
    """Настраиваемое поле гостя или брони; значения — в fields_json записи."""

    __tablename__ = "stays_fields"
    __table_args__ = (UniqueConstraint("target", "code", name="uq_stays_field"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    target: Mapped[str] = mapped_column(String(12))                 # guest | reservation
    code: Mapped[str] = mapped_column(String(32))
    title: Mapped[str] = mapped_column(String(120))
    kind: Mapped[str] = mapped_column(String(8), default="text")    # text | choice | bool | date
    choices_json: Mapped[str] = mapped_column(Text, default="[]")
    searchable: Mapped[bool] = mapped_column(Boolean, default=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=100)


class StaysSettings(Base):
    """Настройки модуля, одна строка id=1 (её заводит ревизия 0008)."""

    __tablename__ = "stays_settings"

    id: Mapped[int] = mapped_column(primary_key=True)
    vip_bonus: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("1"))
    vvip_bonus: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("2"))
    daily_limit: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("8"))
    # коды дня Табеля, при которых назначенному батлеру нужна подмена (отпуск, больничный…)
    replacement_codes: Mapped[str] = mapped_column(String(120), default="ОТ,ДО,Б,ОВ,К")
