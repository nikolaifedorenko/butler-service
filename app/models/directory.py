"""Справочники и ядро каталога: сотрудники, департаменты, службы, виды заявлений,
пользователи, история должностей, блоки графика, периоды трудоустройства, банк часов,
двойные оплаты."""
from __future__ import annotations

import datetime as dt
from typing import TYPE_CHECKING, Optional

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db import Base
from .common import ROLE_EMPLOYEE, utcnow

if TYPE_CHECKING:
    from .cars import Car


class Department(Base):
    __tablename__ = "departments"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)

    employees: Mapped[list[Employee]] = relationship(back_populates="department")


class Subdivision(Base):
    """Справочник служб/подразделений (карточка сотрудника + документы).

    У сотрудника значение хранится текстом (Employee.subdivision) — справочник
    задаёт список вариантов в редакторе; переименование/удаление пункта
    обновляет/очищает карточки (см. API /api/subdivisions)."""

    __tablename__ = "subdivisions"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160), unique=True)


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


class Employee(Base):
    __tablename__ = "employees"

    id: Mapped[int] = mapped_column(primary_key=True)
    full_name: Mapped[str] = mapped_column(String(200))          # Иванов Иван Иванович
    short_name: Mapped[str] = mapped_column(String(120), default="")  # Иванов И.И.
    full_name_genitive: Mapped[str] = mapped_column(String(220), default="")  # «Иванова Ивана Ивановича» — для документов
    position: Mapped[str] = mapped_column(String(120), default="")    # батлер / старший батлер
    phone: Mapped[str] = mapped_column(String(40), default="")
    tab_number: Mapped[str] = mapped_column(String(40), default="")    # табельный номер
    hired_at: Mapped[Optional[dt.date]] = mapped_column(Date, nullable=True)  # дата приёма на работу
    emergency_name: Mapped[str] = mapped_column(String(200), default="")  # контакт близких (экстренно)
    emergency_phone: Mapped[str] = mapped_column(String(40), default="")
    telegram: Mapped[str] = mapped_column(String(64), default="")     # логин Telegram
    email: Mapped[str] = mapped_column(String(120), default="")       # рабочая почта
    dismissed_at: Mapped[Optional[dt.date]] = mapped_column(Date, nullable=True)  # дата увольнения
    nationality: Mapped[str] = mapped_column(String(120), default="")   # гражданство (для документов)
    subdivision: Mapped[str] = mapped_column(String(160), default="")   # служба/подразделение в официальных документах
    department_id: Mapped[Optional[int]] = mapped_column(ForeignKey("departments.id"), nullable=True)
    schedule_group: Mapped[str] = mapped_column(String(80), default="")   # «Смена 1», «Смена 2», «Администрация»
    group_color: Mapped[str] = mapped_column(String(16), default="#8a94a6")  # цвет должности в сетке
    schedule_pattern: Mapped[str] = mapped_column(String(60), default="")  # «2/2», «5/2», «custom:РРВВ» — для продолжения
    schedule_anchor: Mapped[Optional[dt.date]] = mapped_column(Date, nullable=True)  # точка отсчёта цикла
    balance_hours: Mapped[float] = mapped_column(Float, default=0.0)   # стартовый «банк часов»
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    deleted_at: Mapped[Optional[dt.date]] = mapped_column(Date, nullable=True)  # «полное удаление»: скрыт, но в истории

    department: Mapped[Optional[Department]] = relationship(back_populates="employees")
    user: Mapped[Optional[User]] = relationship(back_populates="employee", uselist=False)
    contacts: Mapped[list[EmergencyContact]] = relationship(
        cascade="all, delete-orphan", order_by="EmergencyContact.id")
    # закреплённый электрокар (рекомендательное закрепление): связь нужна, чтобы
    # карточка сотрудника не открывала отдельную сессию на каждого (см. api/employees.py)
    assigned_car: Mapped[Optional[Car]] = relationship(
        back_populates="assigned_employee", uselist=False, foreign_keys="Car.assigned_to")

    @property
    def display_name(self) -> str:
        return self.short_name or self.full_name


class EmergencyContact(Base):
    """Контакты близких для экстренной ситуации — у сотрудника может быть несколько."""

    __tablename__ = "emergency_contacts"

    id: Mapped[int] = mapped_column(primary_key=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    phone: Mapped[str] = mapped_column(String(40), default="")
    relation: Mapped[str] = mapped_column(String(60), default="")   # кем приходится


class PositionHistory(Base):
    """Должности сотрудника с датами: повышения/понижения/переводы видны по периодам."""

    __tablename__ = "position_history"

    id: Mapped[int] = mapped_column(primary_key=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), index=True)
    position: Mapped[str] = mapped_column(String(120))
    start_date: Mapped[dt.date] = mapped_column(Date)
    end_date: Mapped[Optional[dt.date]] = mapped_column(Date, nullable=True)  # None — текущая

    employee: Mapped[Employee] = relationship()


class BlockAssignment(Base):
    """Принадлежность сотрудника блоку графика («Смена 1»/«Смена 2»/…) с датами.
    При переходе между сменами старый период закрывается, новый открывается —
    сотрудник виден в обоих блоках, «чужие» дни заливаются одним цветом."""

    __tablename__ = "block_assignments"
    __table_args__ = (UniqueConstraint("employee_id", "group", "start_date", name="uq_block_emp_group_start"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), index=True)
    group: Mapped[str] = mapped_column(String(80))
    start_date: Mapped[dt.date] = mapped_column(Date)
    end_date: Mapped[Optional[dt.date]] = mapped_column(Date, nullable=True)  # None — текущий блок
    # индивидуальный шаблон графика внутри блока (JSON):
    #   {"kind":"week5","off_weekdays":[6,0],"shift_code":"DAY9"}            — пятидневка со своими выходными
    #   {"kind":"cycle","cycle":"3/3","shift_code":"NIGHT12","anchor":"…"}   — другие смены (3/3, 1/3, РРВВ…)
    #   {"kind":"manual"}                                                    — ячейки заполняются вручную
    # пустая строка — шаблон берётся из общих настроек блока (базовый цикл объекта)
    pattern_json: Mapped[str] = mapped_column(Text, default="")

    employee: Mapped[Employee] = relationship()


class EmploymentPeriod(Base):
    """Периоды работы сотрудника: приём → увольнение → повторный приём.
    Позволяет принять уволенного обратно и показывать в графике только отработанные периоды."""

    __tablename__ = "employment_periods"

    id: Mapped[int] = mapped_column(primary_key=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), index=True)
    start_date: Mapped[dt.date] = mapped_column(Date)
    end_date: Mapped[Optional[dt.date]] = mapped_column(Date, nullable=True)  # None — работает сейчас
    note: Mapped[str] = mapped_column(String(255), default="")
    created_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)

    employee: Mapped[Employee] = relationship()


class BankAdjustment(Base):
    """Ручная корректировка банка часов (плюс/минус) с автором и причиной."""

    __tablename__ = "bank_adjustments"

    id: Mapped[int] = mapped_column(primary_key=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), index=True)
    hours: Mapped[float] = mapped_column(Float, default=0.0)          # со знаком: +4 / -8
    effective_date: Mapped[dt.date] = mapped_column(Date)             # с какой даты учитывается
    reason_code: Mapped[str] = mapped_column(String(32), default="")  # свободная строка;
                                                                      # "OPENING_SEED" — посев
                                                                      # начального банка (R37)
    note: Mapped[str] = mapped_column(String(255), default="")        # «почему»
    author_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    author_name: Mapped[str] = mapped_column(String(120), default="")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)

    employee: Mapped[Employee] = relationship()


class DoublePayDay(Base):
    """День двойной оплаты переработок (по производственному календарю / письму C&B).

    Дни вносятся вручную — обычно на год вперёд. В такой день переработки (часы сверх
    официального окна) выводятся к оплате кодами ДЯ2/ДН2 (двойной тариф).
    scope: shift — только сменные графики (2/2, 3/3…), week5 — только пятидневка, all — все.
    """

    __tablename__ = "double_pay_days"

    id: Mapped[int] = mapped_column(primary_key=True)
    date: Mapped[dt.date] = mapped_column(Date, unique=True, index=True)
    scope: Mapped[str] = mapped_column(String(16), default="all")   # shift | week5 | all
    note: Mapped[str] = mapped_column(String(255), default="")      # «Новогодние праздники», «письмо C&B»
    created_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)


class VipDoublePay(Base):
    """Период работы с ВИП-гостем: переработки сотрудника в эти дни оплачиваются вдвое,
    даже если по производственному календарю день обычный. Если день и так двойной —
    остаётся двойным (тарифы НЕ перемножаются)."""

    __tablename__ = "vip_double_pay"

    id: Mapped[int] = mapped_column(primary_key=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), index=True)
    start_date: Mapped[dt.date] = mapped_column(Date)
    end_date: Mapped[dt.date] = mapped_column(Date)
    note: Mapped[str] = mapped_column(String(255), default="")      # «ВИП-гость: фамилия»
    created_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_by_name: Mapped[str] = mapped_column(String(120), default="")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)

    employee: Mapped[Employee] = relationship()


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(256))
    role: Mapped[str] = mapped_column(String(20), default=ROLE_EMPLOYEE)
    employee_id: Mapped[Optional[int]] = mapped_column(ForeignKey("employees.id"), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)
    token_version: Mapped[int] = mapped_column(Integer, default=0)

    employee: Mapped[Optional[Employee]] = relationship(back_populates="user")


