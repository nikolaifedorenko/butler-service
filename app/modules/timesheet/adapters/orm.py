"""ORM-модели модуля timesheet (адаптер хранения).

Слияние файлов пакета app/models/ (фаза C2, EXECUTION-SPEC-v2 §7):
punch.py (отметки), schedule.py (график и смены), engine_store.py (хранилище
движка) и таймшит-часть directory.py (BlockAssignment, BankAdjustment,
DoublePayDay, VipDoublePay). Каталог персонала (Employee, Department, …) в
фазе C4 переехал в modules/employees/adapters/orm.py. R6 выполнен полностью
(батч 20.10.2026): кросс-модульных relationship нет — FK строками, сотрудники
достаются по employee_id через employees.application (батч-словари в экранах).
Публичная поверхность для других модулей — application/catalog.py.
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
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.core.identity import User  # noqa: F401 — связь Employee.user
from app.core.time import utcnow  # noqa: F401 — default created_at/updated_at

# ────
# ── Блоки графика, банк часов, двойные оплаты (таймшит-часть бывш. directory.py;
# ── каталог персонала — в modules/employees/adapters/orm.py, фаза C4) ──
# ────


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



# User переехал в core/identity.py (фаза C1, 20.10.2026): учётные записи —
# фундамент аутентификации и прав. Employee.user разрешается реестром SQLAlchemy
# (импорт User ниже — для аннотации и явной связи).
# ────
# ── Отметки СКУД/ручные (бывш. models/punch.py) ──
# ────


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

# ────
# ── График и смены (бывш. models/schedule.py) ──
# ────


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
# ────
# ── Хранилище расчётного движка (бывш. models/engine_store.py) ──
# ────


# ═══════════════════════ НОЧНОЙ ОТЧЁТ + ЭЛЕКТРОКАРЫ ═══════════════════════
# Времена событий (created_at/taken_at/…) хранятся в ЛОКАЛЬНОМ времени объекта
# (Europe/Moscow, naive) — как Punch.ts. Для этого нужен now_local(), а не utcnow().


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
    flags_json: Mapped[str] = mapped_column(Text, default="{}")   # снимок FlagsResult (7.2)
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
    # v7/R1: у DeferredBlock нет reason_code — причина неразмещения запись NO_RECEIVER;
    # колонка reason_code старой схемы не мапится (base 15 «Миграция прототипа»)
