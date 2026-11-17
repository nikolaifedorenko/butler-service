"""Модели модуля «Гости»: профиль, связи «кто кому», пожелания к объекту, VIP-коды и определения
настраиваемых полей. Кросс-модульных relationship нет (R6): связь с сотрудниками — строковым FK на
employees.id; брони и проживающие ссылаются на гостей строковым FK из stays."""
from __future__ import annotations

import datetime as dt
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    event,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, Json
from app.core.time import Moment, now


class VipCode(Base):
    """Справочник VIP-кодов гостя (текст до 8 цифр, «03» ≠ «3»): правило сопровождения и
    коэффициент нагрузки. Не версионируется; использованный код архивируется."""

    __tablename__ = "guests_vip_codes"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(8), unique=True)
    title: Mapped[str] = mapped_column(String(80), default="")
    escorted: Mapped[bool] = mapped_column(Boolean, default=False)
    factor: Mapped[Decimal] = mapped_column(Numeric(4, 2), default=Decimal("1"))
    sort_order: Mapped[int] = mapped_column(Integer, default=100)
    archived: Mapped[bool] = mapped_column(Boolean, default=False)


class Guest(Base):
    """Профиль гостя. «Особый гость» и VIP-код — свойства человека; код копируется в его брони."""

    __tablename__ = "guests"

    id: Mapped[int] = mapped_column(primary_key=True)
    last_name: Mapped[str] = mapped_column(String(80))
    first_name: Mapped[str] = mapped_column(String(80), default="")
    middle_name: Mapped[str] = mapped_column(String(80), default="")
    phone: Mapped[str] = mapped_column(String(24), default="")      # нормализованный: +79161234567
    email: Mapped[str] = mapped_column(String(120), default="")
    birth_date: Mapped[Optional[dt.date]] = mapped_column(Date, nullable=True)
    gender: Mapped[str] = mapped_column(String(1), default="")         # m | f | '' (не указан)
    vip_code_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("guests_vip_codes.id", name="fk_guests_vip_code"), nullable=True)
    special: Mapped[bool] = mapped_column(Boolean, default=False)     # «Особый гость»
    preferences: Mapped[dict] = mapped_column(Json, default=dict)
    special_dates: Mapped[list] = mapped_column(Json, default=list)
    fields: Mapped[dict] = mapped_column(Json, default=dict)
    note: Mapped[str] = mapped_column(Text, default="")
    external_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    source: Mapped[str] = mapped_column(String(16), default="")
    # батлер, заведший профиль через семейное дерево: гость — его «свой» (часть 4 §3–§4)
    created_by_employee_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("employees.id", name="fk_guests_created_by"), nullable=True, index=True)
    # нижний регистр Python: SQLite lower() кириллицу не понижает
    search_text: Mapped[str] = mapped_column(String(1000), default="")   # поиск подстрокой: индекс не помогает
    # только ФИО: поиск ниже полного уровня — телефон, почта и поля по нему не ищутся (решение 8)
    name_text: Mapped[str] = mapped_column(String(400), default="", server_default="")
    created_at: Mapped[dt.datetime] = mapped_column(Moment, default=now)
    updated_at: Mapped[dt.datetime] = mapped_column(Moment, default=now, onupdate=now)


def guest_name_text(g: Guest) -> str:
    """Текст поиска по ФИО (нижний регистр Python: SQLite lower() кириллицу не понижает)."""
    return " ".join(p for p in (g.last_name, g.first_name, g.middle_name) if p).lower()[:400]


@event.listens_for(Guest, "before_insert")
@event.listens_for(Guest, "before_update")
def _sync_name_text(_mapper, _conn, g: Guest) -> None:
    # при любой записи профиля через ORM — создание, правка, слияние, демо, импорт
    g.name_text = guest_name_text(g)


class GuestLink(Base):
    """Связь «кто кому»: одна строка, подпись для каждой стороны — LINK_KINDS. Семейные —
    только parent (A — родитель B) и spouse (former — бывшие); остальное родство вычисляется
    (domain/kinship.py)."""

    __tablename__ = "guests_links"
    __table_args__ = (UniqueConstraint("guest_a_id", "guest_b_id", "kind", name="uq_guests_link"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    guest_a_id: Mapped[int] = mapped_column(ForeignKey("guests.id"), index=True)
    guest_b_id: Mapped[int] = mapped_column(ForeignKey("guests.id"), index=True)
    kind: Mapped[str] = mapped_column(String(16))
    former: Mapped[bool] = mapped_column(Boolean, default=False)


class GuestPref(Base):
    """Пожелание гостя к объекту: группа фонда, флаг или конкретный объект; priority — вес: чем больше, тем важнее (счёт объекта — сумма весов выполненных)."""

    __tablename__ = "guests_prefs"
    __table_args__ = (CheckConstraint("kind IN ('group', 'flag', 'unit')", name="ck_guests_prefs_kind"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    guest_id: Mapped[int] = mapped_column(ForeignKey("guests.id"), index=True)
    kind: Mapped[str] = mapped_column(String(8))          # group | flag | unit
    ref_id: Mapped[int] = mapped_column(Integer)
    priority: Mapped[int] = mapped_column(Integer, default=1)


class CustomField(Base):
    """Настраиваемое поле гостя или брони; значения — в колонке fields записи."""

    __tablename__ = "guests_fields"
    __table_args__ = (UniqueConstraint("target", "code", name="uq_guests_field"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    target: Mapped[str] = mapped_column(String(12))                 # guest | reservation
    code: Mapped[str] = mapped_column(String(32))
    title: Mapped[str] = mapped_column(String(120))
    kind: Mapped[str] = mapped_column(String(8), default="text")    # text | choice | bool | date
    choices: Mapped[list] = mapped_column(Json, default=list)
    searchable: Mapped[bool] = mapped_column(Boolean, default=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=100)
