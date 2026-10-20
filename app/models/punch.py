"""Отметки СКУД/ручные (пришёл/ушёл)."""
from __future__ import annotations

import datetime as dt
from typing import TYPE_CHECKING, Optional

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..core.db import Base

if TYPE_CHECKING:
    from .directory import Employee


class Punch(Base):
    """Сырое событие: нажал «Пришёл на работу» / «Ушёл с работы»."""

    __tablename__ = "punches"
    __table_args__ = (Index("ix_punches_emp_ts", "employee_id", "ts"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), index=True)
    ts: Mapped[dt.datetime] = mapped_column(DateTime, index=True)   # локальное время объекта (APP_TZ), naive
    kind: Mapped[str] = mapped_column(String(4))                    # IN | OUT
    source: Mapped[str] = mapped_column(String(16), default="web")  # web | telegram | manual | import
    created_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    note: Mapped[str] = mapped_column(String(255), default="")

    employee: Mapped[Employee] = relationship(lazy="joined")


