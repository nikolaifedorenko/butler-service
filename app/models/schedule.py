"""График и смены: словарь смен и его ревизии, смены (generated/manual),
согласованные отсутствия."""
from __future__ import annotations

import datetime as dt
from typing import TYPE_CHECKING, Optional

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..core.db import Base
from ..core.time import utcnow

if TYPE_CHECKING:
    from .directory import Employee


class ShiftType(Base):
    """Вариант ячейки графика: рабочая смена или отсутствие."""

    __tablename__ = "shift_types"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(20), unique=True)      # DAY12 / NIGHT12 / SICK ...
    name: Mapped[str] = mapped_column(String(120))                  # «08:00–20:00», «больничный»
    kind: Mapped[str] = mapped_column(String(16), default="work")   # work | absence
    start_time: Mapped[str] = mapped_column(String(5), default="")  # "08:00"
    end_time: Mapped[str] = mapped_column(String(5), default="")    # "20:00"
    overnight: Mapped[bool] = mapped_column(Boolean, default=False)
    color: Mapped[str] = mapped_column(String(16), default="#6b7280")
    sort_order: Mapped[int] = mapped_column(Integer, default=100)
    is_working: Mapped[bool] = mapped_column(Boolean, default=True)  # считается ли смена «работой»
    counts_as_worked: Mapped[bool] = mapped_column(Boolean, default=True)  # идёт ли в «отработано» (у больничного — False)
    is_default_off: Mapped[bool] = mapped_column(Boolean, default=False)   # «выходной» по умолчанию
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    # можно ли во время этого отсутствия жать «Пришёл»/«Ушёл» (например,
    # в отпуске отмечаться не нужно). Серверная проверка обоих слоёв режима —
    # api/punches.py::_punch_permissions; помимо вида, режим задаётся в карточке
    # кода Табеля (punch_in/punch_out строки day_code_policy, 16.10.2026).
    # Поячеечных переопределений нет: прежняя schedule_entries — легаси-таблица.
    punch_in_allowed: Mapped[bool] = mapped_column(Boolean, default=True)
    punch_out_allowed: Mapped[bool] = mapped_column(Boolean, default=True)
    # какой документ печатаем по этому отсутствию (ключ из DOC_TYPES); пусто — документ не предлагается
    doc_type: Mapped[str] = mapped_column(String(40), default="")
    archived_at: Mapped[Optional[dt.date]] = mapped_column(Date, nullable=True)  # архив: в прошлом виден, в новых ячейках недоступен

    @property
    def planned_hours(self) -> float:
        if self.kind != "work" or not self.start_time or not self.end_time:
            return 0.0
        h1, m1 = (int(x) for x in self.start_time.split(":"))
        h2, m2 = (int(x) for x in self.end_time.split(":"))
        mins = (h2 * 60 + m2) - (h1 * 60 + m1)
        if mins <= 0:
            mins += 24 * 60
        return round(max(0.0, mins / 60.0), 2)


class ShiftRevision(Base):
    """История словаря смен: какие часы у смены действовали в прошлом.

    Прошлые месяцы графика и табеля считаются по ПРЕЖНИМ значениям смены, поэтому
    удаление смены в словаре — это архивация, а изменение времени не «сдвигает» историю.
    """

    __tablename__ = "shift_revisions"

    id: Mapped[int] = mapped_column(primary_key=True)
    shift_type_id: Mapped[int] = mapped_column(ForeignKey("shift_types.id"), index=True)
    valid_from: Mapped[dt.date] = mapped_column(Date)          # с этой даты действуют значения
    code: Mapped[str] = mapped_column(String(20), default="")
    name: Mapped[str] = mapped_column(String(120), default="")
    kind: Mapped[str] = mapped_column(String(16), default="work")
    start_time: Mapped[str] = mapped_column(String(5), default="")
    end_time: Mapped[str] = mapped_column(String(5), default="")
    overnight: Mapped[bool] = mapped_column(Boolean, default=False)
    color: Mapped[str] = mapped_column(String(16), default="#6b7280")
    is_working: Mapped[bool] = mapped_column(Boolean, default=True)
    counts_as_worked: Mapped[bool] = mapped_column(Boolean, default=True)
    is_default_off: Mapped[bool] = mapped_column(Boolean, default=False)
    doc_type: Mapped[str] = mapped_column(String(40), default="")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)

    shift_type: Mapped[ShiftType] = relationship()


class ScheduleShift(Base):
    """Смена Графика (движок v7.1, 16.3): порождённая из Табеля по окнам CFG-WINDOWS
    (source="generated") либо ручная (source="manual"). Моменты — naive UTC.
    Смена может пересекать полночь; физически не режется — «разрез» логический,
    через ScheduleAbsence (v7/R17). Якорь правки — день начала (date)."""

    __tablename__ = "schedule_shifts"
    __table_args__ = (
        Index("ix_sched_shifts_emp_date", "employee_id", "date"),
        # доска «кто на работе» и статус смены фильтруют по start_utc без employee_id
        Index("ix_sched_shifts_start", "start_utc"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), index=True)
    date: Mapped[dt.date] = mapped_column(Date, index=True)        # день-якорь (день начала)
    start_utc: Mapped[dt.datetime] = mapped_column(DateTime)       # naive UTC
    end_utc: Mapped[dt.datetime] = mapped_column(DateTime)         # naive UTC
    source: Mapped[str] = mapped_column(String(10), default="generated")  # generated | manual
    shift_type_id: Mapped[Optional[int]] = mapped_column(ForeignKey("shift_types.id"), nullable=True)
    note: Mapped[str] = mapped_column(String(255), default="")
    updated_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    employee: Mapped[Employee] = relationship(lazy="joined")


class ScheduleAbsence(Base):
    """Согласованное отсутствие (движок v7.1, 5.1): UTC-интервал, может пересекать
    полночь, длина ≤ 24 ч (CHK-ABSENCE-LENGTH). Используется только флагами и доской
    (RUL-ABSENCE-ONLY-FLAGS). kind — тип отсутствия из словаря (заявление, режим отметок)."""

    __tablename__ = "schedule_absences"
    __table_args__ = (
        Index("ix_sched_abs_emp_start", "employee_id", "start_utc"),
        Index("ix_sched_abs_start", "start_utc"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), index=True)
    start_utc: Mapped[dt.datetime] = mapped_column(DateTime)       # naive UTC
    end_utc: Mapped[dt.datetime] = mapped_column(DateTime)         # naive UTC
    kind_id: Mapped[Optional[int]] = mapped_column(ForeignKey("shift_types.id"), nullable=True)
    note: Mapped[str] = mapped_column(String(255), default="")
    # выбранный сотрудником/менеджером шаблон заявления (18.10.2026): переопределяет
    # привязку вида и точку ввода; пусто — правило по точке ввода (вся смена/интервал)
    doc_type: Mapped[str] = mapped_column(String(40), default="")
    created_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)

    kind: Mapped[Optional[ShiftType]] = relationship(lazy="joined")
    employee: Mapped[Employee] = relationship(lazy="joined")



