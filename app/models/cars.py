"""Поддомен «Электрокары»: места, парк, история, ночные проверки."""
from __future__ import annotations

import datetime as dt
from typing import TYPE_CHECKING, Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..core.db import Base

if TYPE_CHECKING:
    from app.modules.employees.application.catalog import Employee

    from .night import NightReport
from ..core.time import now_local


class CarLocation(Base):
    """Справочник мест парковки/стоянки электрокаров (предустановлены + свои)."""

    __tablename__ = "car_locations"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160), unique=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=100)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    builtin: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=now_local)


class Car(Base):
    """Электрокар. Номер — строка (бывают нечисловые и уникальные имена).

    status: free | busy | charging | maintenance | disabled
      free        — свободен, можно взять;
      busy        — занят (держатель едет/использует);
      charging    — на зарядке (отдельный статус: кар могут поставить заряжаться
                    специально, и он может понадобиться владельцу);
      maintenance — на обслуживании (есть замечания по возврату или завели вручную);
      disabled    — отключён (списан/из ремонта вне учёта) — в обход ночи не попадает.
    assigned_to — закрепление (рекомендательное): ставится в КАРТОЧКЕ СОТРУДНИКА,
                  в карточке кара только отображается.
    """

    __tablename__ = "cars"

    id: Mapped[int] = mapped_column(primary_key=True)
    number: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    status: Mapped[str] = mapped_column(String(16), default="free")
    location: Mapped[str] = mapped_column(String(160), default="")   # текст места (справочник или «своё»)
    charge: Mapped[str] = mapped_column(String(16), default="")      # full | half | empty | ''
    on_charge: Mapped[bool] = mapped_column(Boolean, default=False)  # стоит ли на зарядке (факт)
    canopy: Mapped[bool] = mapped_column(Boolean, default=True)      # тент: отсутствие — просто факт
    condition: Mapped[str] = mapped_column(String(16), default="ok")  # ok | bad
    trash: Mapped[bool] = mapped_column(Boolean, default=False)
    clean: Mapped[bool] = mapped_column(Boolean, default=True)
    has_key: Mapped[bool] = mapped_column(Boolean, default=True)     # ключ у держателя / на месте
    holder_user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    holder_name: Mapped[str] = mapped_column(String(120), default="")  # если держатель внешний — имя текстом
    assigned_to: Mapped[Optional[int]] = mapped_column(ForeignKey("employees.id"), nullable=True)
    note: Mapped[str] = mapped_column(String(255), default="")
    last_checked_at: Mapped[Optional[dt.datetime]] = mapped_column(DateTime, nullable=True)
    last_taken_at: Mapped[Optional[dt.datetime]] = mapped_column(DateTime, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=now_local)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime, default=now_local, onupdate=now_local)

    assigned_employee: Mapped[Optional[Employee]] = relationship(
        back_populates="assigned_car", foreign_keys=[assigned_to])


class CarHistory(Base):
    """История электрокара: журнал событий. Не редактируется и не удаляется —
    только добавляются новые записи (action: take|give|handover_return|return|
    check|status|assign|create|intercept)."""

    __tablename__ = "car_history"
    __table_args__ = (Index("ix_car_history_car_ts", "car_id", "ts"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    car_id: Mapped[int] = mapped_column(ForeignKey("cars.id"), index=True)
    ts: Mapped[dt.datetime] = mapped_column(DateTime, default=now_local)
    action: Mapped[str] = mapped_column(String(24))
    actor_user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    actor_name: Mapped[str] = mapped_column(String(120), default="")
    person: Mapped[str] = mapped_column(String(120), default="")   # кому отдали / кто вернул
    with_key: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    location: Mapped[str] = mapped_column(String(160), default="")
    details_json: Mapped[str] = mapped_column(Text, default="{}")

    car: Mapped[Car] = relationship()


class CarNightCheck(Base):
    """Отметка электрокара внутри шага «Проверка электрокаров» ночного отчёта.

    found=False — «кар не найден» (идёт в замечания супервайзеру);
    found_location — где батлер нашёл кар (место в карточке могло устареть);
    moved=True — батлер ПЕРЕПАРКОВАЛ кар: found_location → location. Это факт,
      а не замечание: видно в обходе, в истории кара и в выгрузке DOCX/PDF;
    location — где кар оставлен после обхода (при перепарковке — новое место);
    checked_at фиксируется фактическое время проверки, поэтому супервайзер видит,
    если кар взяли ПОСЛЕ проверки (car.last_taken_at > checked_at).
    """

    __tablename__ = "car_night_checks"

    id: Mapped[int] = mapped_column(primary_key=True)
    report_id: Mapped[int] = mapped_column(ForeignKey("night_reports.id"), index=True)
    car_id: Mapped[int] = mapped_column(ForeignKey("cars.id"), index=True)
    car_number: Mapped[str] = mapped_column(String(40), default="")
    checker_user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    checker_name: Mapped[str] = mapped_column(String(120), default="")
    checked_at: Mapped[dt.datetime] = mapped_column(DateTime, default=now_local)
    found: Mapped[bool] = mapped_column(Boolean, default=True)
    found_location: Mapped[str] = mapped_column(String(160), default="")  # где нашёл
    location: Mapped[str] = mapped_column(String(160), default="")        # где оставил
    moved: Mapped[bool] = mapped_column(Boolean, default=False)           # перепаркован батлером
    canopy: Mapped[bool] = mapped_column(Boolean, default=True)
    charge: Mapped[str] = mapped_column(String(16), default="")     # full | half | empty
    on_charge: Mapped[bool] = mapped_column(Boolean, default=False)
    condition: Mapped[str] = mapped_column(String(8), default="ok")  # ok | bad
    trash: Mapped[bool] = mapped_column(Boolean, default=False)
    clean: Mapped[bool] = mapped_column(Boolean, default=True)
    comment: Mapped[str] = mapped_column(Text, default="")

    report: Mapped[NightReport] = relationship()


