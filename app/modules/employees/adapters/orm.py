"""ORM-модели модуля employees: каталог персонала (адаптер хранения).

Выделены из app/models/directory.py (фаза C2) и timesheet/adapters/orm.py
(фаза C4, EXECUTION-SPEC-v2 §7 фаза 6): Employee, Department, Subdivision,
StatementKind, EmergencyContact, PositionHistory, EmploymentPeriod. Классы
перенесены без изменений. Связь с core: Employee.user → User (core.identity) — module→core допустим
(R6, батч 20.10.2026: кросс-модульных relationship больше нет — закреплённый
кар читается запросом Car.assigned_to на стороне потребителей). Публичная
поверхность для других модулей — application/catalog.py (R3).

Блоки графика, банк часов и двойные оплаты (BlockAssignment, BankAdjustment,
DoublePayDay, VipDoublePay) остались в timesheet — это домен Табеля/Графика.
"""
from __future__ import annotations

import datetime as dt
from typing import Optional

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.core.identity import User  # noqa: F401 — связь Employee.user
from app.core.time import utcnow  # noqa: F401 — default created_at


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
    # R6 (батч 20.10.2026): связь с core — односторонняя (User.employee удалён);
    # user_id — строковый FK на users, маппер разрешает цель по реестру.
    user: Mapped[Optional[User]] = relationship(uselist=False)
    contacts: Mapped[list[EmergencyContact]] = relationship(
        cascade="all, delete-orphan", order_by="EmergencyContact.id")

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
