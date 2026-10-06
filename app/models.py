"""Модель данных системы учёта рабочего времени."""
from __future__ import annotations

import datetime as dt
from typing import Optional

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base
from .deps import now_local

# ───────────────────────────────────────── роли ─────────────────────────────────────────
ROLE_ADMIN = "admin"          # полный доступ; сам в график не встаёт и не работает
ROLE_MANAGER = "manager"      # права как у admin, но сам может стоять в графике и работать
ROLE_SUPERVISOR = "supervisor"# как manager, но не может создавать/удалять/править supervisor
ROLE_EMPLOYEE = "employee"    # только свои отметки, описания и история своих действий

MANAGER_ROLES = (ROLE_ADMIN, ROLE_MANAGER, ROLE_SUPERVISOR)


def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)


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


class ShiftType(Base):
    """Вариант ячейки графика: рабочая смена или отсутствие."""

    __tablename__ = "shift_types"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(20), unique=True)      # DAY12 / NIGHT12 / SICK ...
    name: Mapped[str] = mapped_column(String(120))                  # «08:00–20:00», «больничный»
    display_code: Mapped[str] = mapped_column(String(12), default="")  # «Я», «Н», «Б», «ОТ», «ДО»
    tzh_code: Mapped[str] = mapped_column(String(12), default="")   # код для официального табеля (Т-13)
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
    # списывать часы этого отсутствия из банка часов (выходной за часы, отпросился на пару часов)
    deduct_from_bank: Mapped[bool] = mapped_column(Boolean, default=False)
    # можно ли во время этой смены/отсутствия жать «Пришёл»/«Ушёл»
    # (например, в отпуске отмечаться не нужно); в отдельной ячейке графика
    # флаг можно переопределить — см. ScheduleEntry.punch_*_override
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
    display_code: Mapped[str] = mapped_column(String(12), default="")
    tzh_code: Mapped[str] = mapped_column(String(12), default="")
    kind: Mapped[str] = mapped_column(String(16), default="work")
    start_time: Mapped[str] = mapped_column(String(5), default="")
    end_time: Mapped[str] = mapped_column(String(5), default="")
    overnight: Mapped[bool] = mapped_column(Boolean, default=False)
    color: Mapped[str] = mapped_column(String(16), default="#6b7280")
    is_working: Mapped[bool] = mapped_column(Boolean, default=True)
    counts_as_worked: Mapped[bool] = mapped_column(Boolean, default=True)
    is_default_off: Mapped[bool] = mapped_column(Boolean, default=False)
    deduct_from_bank: Mapped[bool] = mapped_column(Boolean, default=False)
    doc_type: Mapped[str] = mapped_column(String(40), default="")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)

    shift_type: Mapped[ShiftType] = relationship()


class ScheduleEntry(Base):
    """Ячейка графика: сотрудник × дата."""

    __tablename__ = "schedule_entries"
    __table_args__ = (UniqueConstraint("employee_id", "date", name="uq_schedule_emp_date"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), index=True)
    date: Mapped[dt.date] = mapped_column(Date, index=True)
    shift_type_id: Mapped[int] = mapped_column(ForeignKey("shift_types.id"))
    note: Mapped[str] = mapped_column(Text, default="")
    # частичное отсутствие внутри рабочей смены («отпросился с 14:00 до 16:00»):
    # причина (вид отсутствия) + согласованное окно, в которое сотрудник не работает
    partial_shift_id: Mapped[Optional[int]] = mapped_column(ForeignKey("shift_types.id"), nullable=True)
    from_time: Mapped[str] = mapped_column(String(5), default="")   # "14:00"
    until_time: Mapped[str] = mapped_column(String(5), default="")  # "16:00"
    # явный override флага «можно отмечаться» для этой ячейки:
    # None — как в словаре вида смены/отсутствия, True/False — разрешить/запретить
    punch_in_override: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True, default=None)
    punch_out_override: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True, default=None)
    updated_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    shift_type: Mapped[ShiftType] = relationship(lazy="joined", foreign_keys=[shift_type_id])
    partial_shift: Mapped[Optional[ShiftType]] = relationship(lazy="joined", foreign_keys=[partial_shift_id])
    employee: Mapped[Employee] = relationship(lazy="joined")


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


class TimesheetRow(Base):
    """Расчётная строка табеля за один день (пересчитывается движком)."""

    __tablename__ = "timesheet_rows"
    __table_args__ = (UniqueConstraint("employee_id", "date", name="uq_ts_emp_date"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), index=True)
    date: Mapped[dt.date] = mapped_column(Date, index=True)
    shift_type_id: Mapped[Optional[int]] = mapped_column(ForeignKey("shift_types.id"), nullable=True)
    code: Mapped[str] = mapped_column(String(12), default="")       # код для табеля: Я / Н / Б / ОТ / ДО / В
    planned_hours: Mapped[float] = mapped_column(Float, default=0.0)
    fact_hours: Mapped[float] = mapped_column(Float, default=0.0)
    day_hours: Mapped[float] = mapped_column(Float, default=0.0)    # ДЯ 06:00–22:00
    night_hours: Mapped[float] = mapped_column(Float, default=0.0)  # ДН 22:00–06:00
    ot_hours: Mapped[float] = mapped_column(Float, default=0.0)     # переработка всего (нетто, для банка)
    ot_note: Mapped[str] = mapped_column(Text, default="")          # «с кем работал, что делал»
    pay_ot_day: Mapped[float] = mapped_column(Float, default=0.0)   # брутто-переработка ДЯ (к выплате)
    pay_ot_night: Mapped[float] = mapped_column(Float, default=0.0) # брутто-переработка ДН (к выплате)
    pay_ot_day2: Mapped[float] = mapped_column(Float, default=0.0)  # то же, но в день двойной оплаты (код ДЯ2)
    pay_ot_night2: Mapped[float] = mapped_column(Float, default=0.0) # код ДН2
    double_reason: Mapped[str] = mapped_column(String(16), default="")  # '' | calendar | vip — почему день двойной
    late_hours: Mapped[float] = mapped_column(Float, default=0.0)   # опоздания, ч (для банка/статусов)
    early_hours: Mapped[float] = mapped_column(Float, default=0.0)  # ранние уходы, ч (для банка/статусов)
    unused_hours: Mapped[float] = mapped_column(Float, default=0.0)  # часы официального окна, которые не отработаны
    gap_hours: Mapped[float] = mapped_column(Float, default=0.0)     # несогласованные перерывы внутри смены
    auth_hours: Mapped[float] = mapped_column(Float, default=0.0)    # согласованное отсутствие («отпросился»), ч
    deficit_hours: Mapped[float] = mapped_column(Float, default=0.0)  # недоработка
    timeoff_hours: Mapped[float] = mapped_column(Float, default=0.0)  # списано из банка часов
    fact_in: Mapped[Optional[dt.datetime]] = mapped_column(DateTime, nullable=True)
    fact_out: Mapped[Optional[dt.datetime]] = mapped_column(DateTime, nullable=True)
    planned_start: Mapped[Optional[dt.datetime]] = mapped_column(DateTime, nullable=True)
    planned_end: Mapped[Optional[dt.datetime]] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(24), default="")     # ok|late|early|late_early|gap|no_punch|unclosed|off|absence|work_no_plan|work_off|planned
    detail_json: Mapped[str] = mapped_column(Text, default="[]")    # сессии, клипы, предупреждения
    note: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    shift_type: Mapped[Optional[ShiftType]] = relationship(lazy="joined")
    employee: Mapped[Employee] = relationship(lazy="joined")


class Setting(Base):
    """Ключ/значение — правила расчёта, редактируются в веб-интерфейсе."""

    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(String(255), default="")
    description: Mapped[str] = mapped_column(String(255), default="")


# ═══════════════════════ НОЧНОЙ ОТЧЁТ + ЭЛЕКТРОКАРЫ ═══════════════════════
# Времена событий (created_at/taken_at/…) хранятся в ЛОКАЛЬНОМ времени объекта
# (Europe/Moscow, naive) — как Punch.ts. Для этого нужен now_local(), а не utcnow().


class NightArea(Base):
    """Справочник областей ночной проверки (виллы, спа, бассейн, ресепшн…).

    name       — отображаемое название («Вилла VEG 4001», «Спа»);
    category   — категория области («VEG», «VPS», «Офис»): пункты чек-листа
                 привязаны к категории, поэтому у всех вилл одной категории
                 список пунктов одинаковый;
    active     — выключенные области не попадают в новые ночные отчёты
                 (созданные ранее отчёты не меняются: там лежит снимок).
    """

    __tablename__ = "night_areas"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160), unique=True)
    category: Mapped[str] = mapped_column(String(80), default="")
    sort_order: Mapped[int] = mapped_column(Integer, default=100)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=now_local)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime, default=now_local, onupdate=now_local)


class ChecklistItem(Base):
    """Пункт чек-листа области (ведётся админом/менеджером). Привязан к категории."""

    __tablename__ = "checklist_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    area_id: Mapped[int] = mapped_column(ForeignKey("night_areas.id"), index=True)
    text: Mapped[str] = mapped_column(String(300))
    sort_order: Mapped[int] = mapped_column(Integer, default=100)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=now_local)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime, default=now_local, onupdate=now_local)

    area: Mapped[NightArea] = relationship()


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

    snapshot_json — [{"id": <item_id>, "text": "..."}]: правки справочников после
    создания отчёта его не ломают.
    """

    __tablename__ = "night_area_sections"
    __table_args__ = (UniqueConstraint("report_id", "area_id", name="uq_night_section_area"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    report_id: Mapped[int] = mapped_column(ForeignKey("night_reports.id"), index=True)
    area_id: Mapped[Optional[int]] = mapped_column(ForeignKey("night_areas.id"), nullable=True)
    name: Mapped[str] = mapped_column(String(160))
    category: Mapped[str] = mapped_column(String(80), default="")
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
    text: Mapped[str] = mapped_column(String(300))
    sort_order: Mapped[int] = mapped_column(Integer, default=100)
    answer: Mapped[str] = mapped_column(String(8), default="")   # '' (не отмечено) | ok | bad
    comment: Mapped[str] = mapped_column(Text, default="")
    answered_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    answered_by_name: Mapped[str] = mapped_column(String(120), default="")
    answered_at: Mapped[Optional[dt.datetime]] = mapped_column(DateTime, nullable=True)

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
    location: Mapped[str] = mapped_column(String(160), default="")
    canopy: Mapped[bool] = mapped_column(Boolean, default=True)
    charge: Mapped[str] = mapped_column(String(16), default="")     # full | half | empty
    on_charge: Mapped[bool] = mapped_column(Boolean, default=False)
    condition: Mapped[str] = mapped_column(String(8), default="ok")  # ok | bad
    trash: Mapped[bool] = mapped_column(Boolean, default=False)
    clean: Mapped[bool] = mapped_column(Boolean, default=True)
    comment: Mapped[str] = mapped_column(Text, default="")

    report: Mapped[NightReport] = relationship()


class Photo(Base):
    """Фотографии (комментарии к «Не ОК», замечания по возврату кара).

    Храним оригиналы на диске в data/uploads/YYYY/MM/, путь относительно BASE_DIR.
    Срок хранения настраивается (photo_retention_days): старые файлы удаляет
    cleanup_photos() при старте сервера; запись остаётся (url пустой, missing=True).
    """

    __tablename__ = "photos"

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(32), index=True)   # night_item | car_return | car_check
    ref_id: Mapped[int] = mapped_column(Integer, index=True)    # id связанной записи
    filename: Mapped[str] = mapped_column(String(255), default="")
    path: Mapped[str] = mapped_column(String(400), default="")  # относительный путь от корня проекта
    size: Mapped[int] = mapped_column(Integer, default=0)
    uploaded_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    uploaded_by_name: Mapped[str] = mapped_column(String(120), default="")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=now_local)


class AuditLog(Base):
    """Кто и что менял (график, ручные отметки, настройки)."""

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    ts: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow, index=True)
    actor_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    actor_name: Mapped[str] = mapped_column(String(120), default="")
    action: Mapped[str] = mapped_column(String(64))
    target: Mapped[str] = mapped_column(String(200), default="")
    payload_json: Mapped[str] = mapped_column(Text, default="{}")

    actor: Mapped[Optional[User]] = relationship()


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
    reason_code: Mapped[str] = mapped_column(String(32), default="NO_RECEIVER")


class AccessGroup(Base):
    """Группа прав доступа (произвольная: «Старшие смены», «Бухгалтерия» …)."""

    __tablename__ = "access_groups"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80), unique=True)
    description: Mapped[str] = mapped_column(String(255), default="")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)


class AccessGroupMember(Base):
    __tablename__ = "access_group_members"
    __table_args__ = (UniqueConstraint("group_id", "user_id", name="uq_access_member"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("access_groups.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)


class AccessGrant(Base):
    """Право: для группы ИЛИ для пользователя; effect allow/deny. Индивидуальное — сильнее группового."""

    __tablename__ = "access_grants"

    id: Mapped[int] = mapped_column(primary_key=True)
    group_id: Mapped[Optional[int]] = mapped_column(ForeignKey("access_groups.id"), nullable=True, index=True)
    user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    role: Mapped[str] = mapped_column(String(20), default="")       # переопределение базовой роли
    permission: Mapped[str] = mapped_column(String(48))
    effect: Mapped[str] = mapped_column(String(8), default="allow")  # allow | deny
